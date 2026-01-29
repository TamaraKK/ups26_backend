import json
import argparse
from esp_coredump import CoreDump
from esp_coredump.corefile.elf import ESPCoreDumpElfFile, EspTaskStatus, TASK_STATUS_CORRECT
from esp_coredump.corefile.gdb import EspGDB
from construct import Struct, GreedyRange, Int32ul
from esp_coredump.corefile import xtensa
from esp_coredump.corefile.elf import ElfSegment


class CoreDumpDecoder(CoreDump):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.output = {}

    def get_crashed_task_info(self, marker):
        if marker == ESPCoreDumpElfFile.CURR_TASK_MARKER:
            return {'error': 'Crashed task has been skipped.'}
        else:
            task_name = self.gdb_esp.get_freertos_task_name(marker)
            return {
                'handle': f'0x{marker:x}',
                'name': task_name,
                
            }

    def get_isr_context(self, extra_info):
        if self.exe_elf.e_machine == ESPCoreDumpElfFile.EM_XTENSA:
            isr_ctx_idx = 37
        else:
            isr_ctx_idx = 1
        if len(extra_info) < isr_ctx_idx + 1:
            return {'in_isr': False}
        return {'in_isr': extra_info[isr_ctx_idx] != 0}

    def get_current_thread_registers(self, extra_note, extra_info):
        regs = {}
        if self.exe_elf.e_machine == ESPCoreDumpElfFile.EM_XTENSA:
            if extra_note and extra_info:
                regs['exception_registers'] = "present"
            else:
                regs['exception_registers'] = "not found"

        return regs

    def get_current_thread_stack(self, task_info):
        stack = {}
        try:
            backtrace_text = self.gdb_esp.run_cmd('bt')
            stack['parsed'] = self.parse_backtrace(backtrace_text, is_current_thread=True)
        except Exception as e:
            stack['error'] = f"Error getting backtrace: {e}"
            stack['raw'] = str(e)

        if task_info and task_info[0].task_flags != TASK_STATUS_CORRECT:
            stack['corrupted'] = True
            stack['info'] = {
                'index': task_info[0].task_index,
                'flags': task_info[0].task_flags,
                'addr': task_info[0].task_tcb_addr,
                'start': task_info[0].task_stack_start}
            
        return stack
    

    def get_threads_info(self, task_info):
        threads_info = {}
        
        threads, _ = self.gdb_esp.get_thread_info()
        if not threads:
            threads_info['error'] = 'Could not retrieve threads information.'
            return threads_info
            
        thread_list = []
        for thr in threads:
            thr_id = int(thr['id'])
            tcb_addr = self.gdb_esp.gdb2freertos_thread_id(thr['target-id'])
            task_name = self.gdb_esp.get_freertos_task_name(tcb_addr)
            
            try:
                pxEndOfStack = int(self.gdb_esp.parse_tcb_variable(tcb_addr, 'pxEndOfStack'), 16)
                pxTopOfStack = int(self.gdb_esp.parse_tcb_variable(tcb_addr, 'pxTopOfStack'), 16)
                pxStack = int(self.gdb_esp.parse_tcb_variable(tcb_addr, 'pxStack'), 16)
                uxPriority = int(self.gdb_esp.parse_tcb_variable(tcb_addr, 'uxPriority'), 16)
                uxBasePriority = int(self.gdb_esp.parse_tcb_variable(tcb_addr, 'uxBasePriority'), 16)
            except ValueError:
                pxEndOfStack = pxTopOfStack = pxStack = uxPriority = uxBasePriority = 0

            thread_dict = {
                'id': thr_id,
                'tcb_addr': f'0x{tcb_addr:x}',
                'task_name': task_name,
            }

            if pxStack == 0:
                thread_dict['error'] = 'Corrupted TCB data'
            else:
                thread_dict['priority'] = f'{uxPriority}/{uxBasePriority}'
                thread_dict['stack-usage'] = f'{abs(pxEndOfStack - pxTopOfStack)}/{abs(pxStack - pxTopOfStack)}'

            self.gdb_esp.switch_thread(thr_id)
            try:
                backtrace_text = self.gdb_esp.run_cmd('bt')
                thread_dict['backtrace'] = self.parse_backtrace(backtrace_text)
            except Exception as e:
                thread_dict['backtrace'] = {'error': f"Error getting backtrace: {e}"}

            if task_info and task_info[thr_id - 1].task_flags != TASK_STATUS_CORRECT:
                thread_dict['corrupted'] = True
                thread_dict['task-info'] = {
                    'index': task_info[thr_id - 1].task_index,
                    'flags': task_info[thr_id - 1].task_flags,
                    'tcb-addr': task_info[thr_id - 1].task_tcb_addr,
                    'stack-start': task_info[thr_id - 1].task_stack_start,
                }
            thread_list.append(thread_dict)

        return thread_list


    def parse_backtrace(self, backtrace_text, is_current_thread=False):
        
        lines = backtrace_text.strip().split('\n')
        frames = []

        for line in lines:
            line = line.strip()
            if not line.startswith('#'):
                continue

            # Parse frame like: #3  0x400d66bc in fail_once (unused=97 'a') at file.c:14
            try:
                parts = line.split(' in ', 1)
                if len(parts) < 2:
                    frames.append({'raw': line, 'parsed': False})
                    continue

                # Get frame number and address
                frame_part = parts[0].strip()
                frame_num = frame_part.split()[0][1:]  # Remove '#'
                addr = frame_part.split()[1] if len(frame_part.split()) > 1 else None

                # Get function and rest
                rest = parts[1].strip()

                frame = {
                    'frame': int(frame_num),
                    'address': addr,
                    'user-code?': False,
                    'system-code?': False,
                    'unknown?': False,
                }

                if '?? ()' in rest:
                    frame['function'] = 'unknown'
                    frame['unknown?'] = True
                elif ' at ' in rest:
                    
                    func_part, location = rest.split(' at ', 1)
                    if '(' in func_part:
                        func_name, args = func_part.split('(', 1)
                        frame['function'] = func_name.strip()
                        frame['arguments'] = '(' + args.strip()
                    else:
                        frame['function'] = func_part.strip()

                    frame['location'] = location.strip()

                    if  '/Users/' in location:
                        frame['user-code?'] = True
                        frame['file'] = location.split('/')[-1].split(':')[0]
                        frame['line'] = int(location.split(':')[-1])
                    else:
                        frame['system-code?'] = True
                else:
                    
                    if '(' in rest:
                        func_name, args = rest.split('(', 1)
                        frame['function'] = func_name.strip()
                        frame['arguments'] = '(' + args.strip()
                    else:
                        frame['function'] = rest.strip()
                    frame['system-code?'] = True

                frames.append(frame)

            except Exception as e:
                frames.append({'raw': line, 'error': str(e)})

        root_cause = None
        for frame in frames:
            if frame.get('user-code?'):
                root_cause = frame
                break

        user_frames = sum(1 for f in frames if f.get('user-code?'))
        system_frames = sum(1 for f in frames if f.get('system-code?'))

        return {
            'frames': frames,
            'summary': {
                'total-frames': len(frames),
                'user-frames': user_frames,
                'system-frames': system_frames,
                'unknown-frames': len(frames) - user_frames - system_frames,
                'root-cause': root_cause,
            }
        }

    def get_all_memory_regions(self):
        regions = []
        core_segs = self.core_elf.load_segments
        merged_segs = []
        for sec in self.exe_elf.sections:
            merged = False
            for seg in core_segs:
                if seg.addr <= sec.addr <= seg.addr + len(seg.data):
                    seg_addr = seg.addr
                    if seg.addr + len(seg.data) <= sec.addr + len(sec.data):
                        seg_len = len(sec.data) + (sec.addr - seg.addr)
                    else:
                        seg_len = len(seg.data)
                    merged_segs.append((sec.name, seg_addr, seg_len, sec.attr_str(), True))
                    core_segs.remove(seg)
                    merged = True
                elif sec.addr <= seg.addr <= sec.addr + len(sec.data):
                    seg_addr = sec.addr
                    if (seg.addr + len(seg.data)) >= (sec.addr + len(sec.data)):
                        seg_len = len(sec.data) + (seg.addr + len(seg.data)) - (sec.addr + len(sec.data))
                    else:
                        seg_len = len(sec.data)
                    merged_segs.append((sec.name, seg_addr, seg_len, sec.attr_str(), True))
                    core_segs.remove(seg)
                    merged = True

            if not merged:
                merged_segs.append((sec.name, sec.addr, len(sec.data), sec.attr_str(), False))

        for ms in merged_segs:
            regions.append({'name': ms[0], 'address': f'0x{ms[1]:x}', 'size': f'0x{ms[2]:x}', 'attrs': ms[3]})

        for cs in core_segs:
            if cs.flags & ElfSegment.PF_X:
                seg_name = 'rom.text'
            else:
                seg_name = 'tasks.data'
            regions.append({'name': f'.coredump.{seg_name}', 'address': f'0x{cs.addr:x}', 'size': f'0x{len(cs.data):x}', 'attrs': cs.attr_str()})
            
        return regions

    def get_core_dump_memory_contents(self):
        mem_contents = []
        for cs in self.core_elf.load_segments:
            if cs.flags & ElfSegment.PF_X:
                seg_name = 'rom.text'
            else:
                seg_name = 'tasks.data'
            
            content = {
                'name': f'.coredump.{seg_name}',
                'address': f'0x{cs.addr:x}',
                'size': f'0x{len(cs.data):x}',
                'attrs': cs.attr_str(),
                'dump': self.gdb_esp.run_cmd(f'x/{len(cs.data) // 4}dx 0x{cs.addr:x}')
            }
            mem_contents.append(content)
        return mem_contents

    def info_corefile(self):
        
        with self._handle_coredump_loader_error():
            self.exe_elf = ESPCoreDumpElfFile(self.prog)
            core_header_info_dict = self.get_core_header_info_dict(e_machine=self.exe_elf.e_machine)
            self.core_elf = ESPCoreDumpElfFile(core_header_info_dict['core_elf_path'])

        temp_files = core_header_info_dict.pop('temp_files')
        self.chip = self.verify_target(core_header_info_dict)

        if self.exe_elf.e_machine != self.core_elf.e_machine:
            raise ValueError('The arch should be the same between core elf and exe elf')

        task_info, extra_note = self.get_task_info_extra_note_tuple()

        self.output['start?'] = True

        gdb_args = self.get_gdb_args(is_dbg_mode=False, **core_header_info_dict)

        self.gdb_esp = EspGDB(gdb_args, timeout_sec=self.gdb_timeout_sec)

        extra_info = None
        if extra_note:
            extra_info_struct = Struct('regs' / GreedyRange(Int32ul)).parse(extra_note.desc)
            if extra_info_struct and hasattr(extra_info_struct, 'regs'):
                extra_info = extra_info_struct.regs
                if extra_info:
                    marker = extra_info[0]
                    self.output['crashed-task'] = self.get_crashed_task_info(marker)
                    self.output['isr-context'] = self.get_isr_context(extra_info)

        panic_details = self.get_panic_details()
        if panic_details:

            reason = panic_details.desc.decode('utf-8')

            self.output['reason'] = reason

            if 'abort()' in reason:
                self.output['type'] = 'abort'

            elif 'assert' in reason.lower():
                self.output['type'] = 'assert'

            elif 'watchdog' in reason.lower():
                self.output['type'] = 'watchdog'


        self.output['current-thread-registers'] = self.get_current_thread_registers(extra_note, extra_info)
        self.output['current-thread-stack'] = self.get_current_thread_stack(task_info)
        self.output['threads'] = self.get_threads_info(task_info)
        self.output['all-memory-regions'] = self.get_all_memory_regions()

        if self.print_mem:
            self.output['core-dump-memory-contents'] = self.get_core_dump_memory_contents()

        self.output['end?'] = True

        del self.gdb_esp

        return self.output

def main():
    parser = argparse.ArgumentParser(description='ESP32 Core Dump Utility')
    parser.add_argument('--prog', help='Path to program ELF file', required=True)
    parser.add_argument('--core', help='Path to core dump file', required=True)
    parser.add_argument('--save-core', help='Save core dump to file')
    parser.add_argument('--off', type=int, help='Offset of core dump partition on flash')
    parser.add_argument('--gdb-timeout-sec', type=int, default=10, help='GDB timeout')
    parser.add_argument('--chip', default='auto', help='Target chip type')
    
    args = parser.parse_args()

    coredump = CoreDumpDecoder(
        prog=args.prog,
        core=args.core,
        save_core=args.save_core,
        off=args.off,
        gdb_timeout_sec=args.gdb_timeout_sec,
        chip=args.chip,
    )
    json_output = coredump.info_corefile()
    print(json.dumps(json_output))

if __name__ == '__main__':
    main()
