#!/usr/bin/env python3
"""Memory monitoring for PostPilot"""
import psutil
import time
import os

def get_memory_usage():
    """Get memory usage of PostPilot processes"""
    total_mb = 0
    processes = []
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if any(keyword in cmdline.lower() for keyword in ['uvicorn', 'streamlit', 'python3.*app']):
                mem_mb = proc.info['memory_info'].rss / 1024 / 1024
                total_mb += mem_mb
                processes.append({
                    'pid': proc.info['pid'],
                    'name': proc.info['name'],
                    'mem_mb': mem_mb,
                    'cmd': cmdline[:50] + '...' if len(cmdline) > 50 else cmdline
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    return total_mb, processes

def main():
    print("PostPilot Memory Monitor")
    print("=" * 50)
    
    while True:
        total_mb, processes = get_memory_usage()
        
        # Clear screen
        os.system('clear' if os.name == 'posix' else 'cls')
        
        print(f"Total Memory Usage: {total_mb:.1f} MB")
        print(f"System Available: {psutil.virtual_memory().available / 1024 / 1024:.1f} MB")
        print("-" * 50)
        
        for proc in sorted(processes, key=lambda x: x['mem_mb'], reverse=True):
            print(f"{proc['mem_mb']:6.1f} MB | PID {proc['pid']:6d} | {proc['cmd']}")
        
        print("\nPress Ctrl+C to stop monitoring...")
        time.sleep(5)

if __name__ == "__main__":
    main()
