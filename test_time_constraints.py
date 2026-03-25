import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import sys
import os

# Add root to sys.path
sys.path.append(os.getcwd())

import MetaTrader5 as mt5
import execution.mt5_executor as executor
from config import (
    TRADE_START_HOUR, TRADE_STOP_HOUR, 
    CLOSE_PROFIT_HOUR, CLOSE_ALL_HOUR, CLOSE_ALL_MINUTE, 
    SYMBOLS, DAILY_PROFIT_TARGET_PCT, PROFIT_LOCK_THRESH
)

def run_diagnostic():
    print("=" * 60)
    print("  Time Constraint Diagnostic")
    print("=" * 60)
    
    if not mt5.initialize():
        print(f"❌ Failed to initialize MT5: {mt5.last_error()}")
        return

    symbol = SYMBOLS[0]
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        print(f"❌ Could not fetch server time for {symbol}.")
        mt5.shutdown()
        return

    # server_dt is MT5's view. Local time is for comparison/reference.
    server_dt = datetime.fromtimestamp(tick.time, timezone.utc)
    print(f"✅ MT5 Server Time: {server_dt.strftime('%A, %Y-%m-%d %H:%M:%S')}")
    print(f"⌚ Local Time (PC): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. Trading Window Check
    is_weekend = server_dt.weekday() >= 5
    in_window = False
    if not is_weekend:
        if TRADE_START_HOUR < TRADE_STOP_HOUR:
            in_window = TRADE_START_HOUR <= server_dt.hour < TRADE_STOP_HOUR
        else:
            in_window = server_dt.hour >= TRADE_START_HOUR or server_dt.hour < TRADE_STOP_HOUR

    print("\n--- Trading Window Status ---")
    if is_weekend:
        print(f"🔴 WEEKEND: Trading is disabled (Saturday/Sunday).")
    elif in_window:
        print(f"🟢 OPEN: Trading window is ACTIVE ({TRADE_START_HOUR:02}:00 - {TRADE_STOP_HOUR:02}:00).")
    else:
        print(f"🟡 CLOSED: Outside trading window. No NEW trades will be opened.")

    # 2. Closure Management Check
    print("\n--- Position Management Status ---")
    
    # Simulate current server state
    hour = server_dt.hour
    minute = server_dt.minute
    
    close_all = False
    if hour == CLOSE_ALL_HOUR and minute >= CLOSE_ALL_MINUTE:
        close_all = True
        print(f"🚨 CRITICAL: Past {CLOSE_ALL_HOUR}:{CLOSE_ALL_MINUTE:02}. Closing ALL positions.")
    elif hour == CLOSE_PROFIT_HOUR:
         print(f"⚠️  WARNING: Past {CLOSE_PROFIT_HOUR}:00. Closing PROFITABLE positions.")
    else:
        print(f"⏳ Normal Operation: Monitoring for trailing stops/TP/SL.")

    # 3. Model Retraining Check
    print("\n--- Model Retraining ---")
    print(f"🔄 Model will automatically restart at Midnight (00:00:00).")

    # 4. Daily Profit Target Diagnostic
    print("\n--- Daily Profit Target ---")
    account = mt5.account_info()
    if account:
        print(f"💰 Account Balance: {account.balance:.2f} {account.currency}")
        print(f"📈 Account Equity:  {account.equity:.2f} {account.currency}")
        # Note: start_day_capital is tracked by main.py at runtime.
        # Here we just show the 15% target level.
        target_amount = account.balance * (DAILY_PROFIT_TARGET_PCT / 100.0)
        print(f"🎯 15% Target:     +${target_amount:.2f}")
        print(f"💵 Lock Threshold: ${PROFIT_LOCK_THRESH} (Close > $20, TP = $20 for others)")
    else:
        print("❌ Could not retrieve account info.")

    mt5.shutdown()
    print("=" * 60 + "\n")

# Mocking for Unit Tests - Store original MT5 if needed or just replace for the tests
import unittest
from unittest.mock import MagicMock, patch

class TestTimeConstraints(unittest.TestCase):

    def setUp(self):
        # We patch MT5 for all tests in this class
        self.patcher_sym = patch('MetaTrader5.symbol_info')
        self.patcher_tick = patch('MetaTrader5.symbol_info_tick')
        self.mock_sym = self.patcher_sym.start()
        self.mock_tick = self.patcher_tick.start()
        
        # Configure default mock behaviors
        sym_info = MagicMock()
        sym_info.digits = 5
        sym_info.point = 0.00001
        self.mock_sym.return_value = sym_info
        
        tick = MagicMock()
        tick.bid = 1.1000
        tick.ask = 1.1005
        self.mock_tick.return_value = tick

    def tearDown(self):
        self.patcher_sym.stop()
        self.patcher_tick.stop()

    @patch('MetaTrader5.positions_get')
    def test_manage_time_based_closes_profit_at_2305(self, mock_pos_get):
        """Verify profitable positions close after 11 PM."""
        test_time = datetime(2024, 5, 20, 23, 5)
        
        p_profit = MagicMock(ticket=1, profit=10.0, symbol="EURUSD", type=0, volume=0.1)
        p_loss = MagicMock(ticket=2, profit=-5.0, symbol="EURUSD", type=0, volume=0.1)
        mock_pos_get.return_value = (p_profit, p_loss)
        
        with patch('execution.mt5_executor.close_position') as mock_close:
            executor.manage_time_based_closes(test_time)
            # Should only call close for the profitable one
            self.assertEqual(mock_close.call_count, 1)
            # Use the tick return value that executor.manage_time_based_closes internally fetches
            mock_close.assert_called_with(p_profit, self.mock_tick.return_value)

    @patch('MetaTrader5.positions_get')
    def test_manage_time_based_closes_all_at_2335(self, mock_pos_get):
        """Verify all positions close after 11:30 PM."""
        test_time = datetime(2024, 5, 20, 23, 35)
        
        p_profit = MagicMock(ticket=1, profit=10.0, symbol="EURUSD", type=0, volume=0.1)
        p_loss = MagicMock(ticket=2, profit=-5.0, symbol="EURUSD", type=0, volume=0.1)
        mock_pos_get.return_value = (p_profit, p_loss)
        
        with patch('execution.mt5_executor.close_position') as mock_close:
            executor.manage_time_based_closes(test_time)
            # Should call close for both
            self.assertEqual(mock_close.call_count, 2)

    @patch('MetaTrader5.positions_get')
    def test_no_close_at_Midday(self, mock_pos_get):
        """Verify no closures happen at Noon."""
        test_time = datetime(2024, 5, 20, 12, 0)
        mock_pos_get.return_value = (MagicMock(),)
        
        with patch('execution.mt5_executor.close_position') as mock_close:
            executor.manage_time_based_closes(test_time)
            mock_close.assert_not_called()

    @patch('MetaTrader5.positions_get')
    @patch('MetaTrader5.order_send')
    def test_lock_in_profits(self, mock_order_send, mock_pos_get):
        """Verify lock_in_profits functionality."""
        from config import PROFIT_LOCK_THRESH
        
        # 1. Position with profit > $20 -> Should close
        p_big_profit = MagicMock(ticket=10, profit=PROFIT_LOCK_THRESH + 5.0, symbol="EURUSD", type=0, volume=0.1)
        # 2. Position with profit < $20 -> Should update TP
        p_small_profit = MagicMock(ticket=11, profit=5.0, symbol="EURUSD", type=0, volume=0.1, price_open=1.1000, sl=1.0900, tp=1.2000)
        
        mock_pos_get.return_value = (p_big_profit, p_small_profit)
        mock_order_send.return_value.retcode = 10009 # mt5.TRADE_RETCODE_DONE
        
        # We need mock_sym for the tick_value calculation in mt5_executor.py
        self.mock_sym.return_value.trade_tick_value = 1.0
        self.mock_sym.return_value.trade_tick_size = 0.00001
        self.mock_sym.return_value.digits = 5
        
        with patch('execution.mt5_executor.close_position') as mock_close:
            executor.lock_in_profits()
            
            # Big profit should be closed
            mock_close.assert_called_once()
            self.assertEqual(mock_close.call_args[0][0].ticket, 10)
            
            # Small profit should have order_send called to update TP
            # Verify order_send was called (once for close, once for TP)
            # Actually close_position calls order_send too.
            # In our mock setup, both are tracked.
            self.assertTrue(mock_order_send.called)

if __name__ == "__main__":
    run_diagnostic()
    
    print("Running Logic Verification Tests (Mocks)...")
    # Redirect stdout to capture unittest output if needed, but here we just run it
    unittest.main()
