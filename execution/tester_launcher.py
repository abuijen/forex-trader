"""
tester_launcher.py
──────────────────
Generates an MT5 Strategy Tester .ini file and launches the terminal in tester mode.
"""

import os
import subprocess
import MetaTrader5 as mt5
from config import MT5_PATH, SYMBOLS, TIMEFRAME, TESTER_CONFIG_FILE

def generate_tester_ini(symbol, timeframe, expert_path, config_path):
    """
    Creates the .ini configuration file for MT5 strategy tester.
    """
    # Model 4 = Every tick based on real ticks
    # ExecutionMode 1 = Random delay
    
    # Map timeframe integer to MT5 string
    tf_map = {1: "M1", 5: "M5", 15: "M15", 30: "M30", 60: "H1", 240: "H4", 1440: "D1"}
    tf_str = tf_map.get(timeframe, "M5")
    
    ini_content = f"""
[Tester]
Expert={expert_path}
Symbol={symbol}
Period={tf_str}
Model=4
ExecutionMode=1
Optimization=0
ReplaceReport=1
ShutdownTerminal=0
Deposit=10000
Currency=USD
Leverage=100
Visual=1
"""
    with open(config_path, "w") as f:
        f.write(ini_content.strip())
    print(f"[tester] Generated config at {config_path}")

def launch_tester():
    """
    Launches MT5 with the /tester flag.
    """
    # Use the first symbol and timeframe from config
    symbol = SYMBOLS[0]
    expert_path = os.path.abspath("main.py")
    config_path = os.path.abspath(TESTER_CONFIG_FILE)
    
    generate_tester_ini(symbol, TIMEFRAME, expert_path, config_path)
    
    cmd = [MT5_PATH, f"/config:{config_path}"]
    print(f"[tester] Launching MT5 Strategy Tester: {' '.join(cmd)}")
    
    try:
        # We start it as a separate process so the dashboard/script doesn't hang
        subprocess.Popen(cmd)
        return True
    except Exception as e:
        print(f"[tester] Error launching MT5: {e}")
        return False

if __name__ == "__main__":
    launch_tester()
