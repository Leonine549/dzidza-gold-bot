import os
import logging
import requests
import pandas as pd
import ta
from datetime import datetime
from typing import Tuple, Dict, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dzidza_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
class Config:
    OANDA_URL = os.getenv("OANDA_URL", "https://api-fxpractice.oanda.com/v3/instruments/XAU_USD/candles")
    API_KEY = os.getenv("OANDA_API_KEY")
    ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
    GRANULARITY = os.getenv("GRANULARITY", "M5")
    CANDLE_COUNT = int(os.getenv("CANDLE_COUNT", "100"))
    RISK_PERCENTAGE = float(os.getenv("RISK_PERCENTAGE", "1.0"))
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
    TIMEOUT = int(os.getenv("TIMEOUT", "10"))

class GoldTradingBot:
    def __init__(self):
        self.config = Config
        self.trade_history = []
        self.validate_config()
    
    def validate_config(self) -> None:
        """Validate required configuration"""
        if not self.config.API_KEY:
            logger.error("API_KEY not found in environment variables")
            raise ValueError("OANDA_API_KEY is required")
        if not self.config.ACCOUNT_ID:
            logger.error("ACCOUNT_ID not found in environment variables")
            raise ValueError("OANDA_ACCOUNT_ID is required")
        logger.info("Configuration validated successfully")
    
    def fetch_gold_data(self, retries: int = 0) -> Optional[pd.DataFrame]:
        """Fetch gold data with retry logic"""
        try:
            headers = {"Authorization": f"Bearer {self.config.API_KEY}"}
            params = {
                "granularity": self.config.GRANULARITY,
                "count": self.config.CANDLE_COUNT
            }
            response = requests.get(
                self.config.OANDA_URL,
                headers=headers,
                params=params,
                timeout=self.config.TIMEOUT
            )
            response.raise_for_status()
            
            data = response.json()["candles"]
            df = pd.DataFrame([{
                "time": c["time"],
                "open": float(c["mid"]["o"]),
                "high": float(c["mid"]["h"]),
                "low": float(c["mid"]["l"]),
                "close": float(c["mid"]["c"]),
                "volume": int(c.get("volume", 0))
            } for c in data])
            
            df["time"] = pd.to_datetime(df["time"])
            logger.info(f"Successfully fetched {len(df)} candles")
            return df
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"API request failed (attempt {retries + 1}/{self.config.MAX_RETRIES}): {e}")
            if retries < self.config.MAX_RETRIES - 1:
                import time
                wait_time = 2 ** retries  # Exponential backoff
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                return self.fetch_gold_data(retries + 1)
            else:
                logger.error("Max retries reached. Unable to fetch data.")
                return None
    
    def apply_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply technical indicators"""
        try:
            # Trend indicators
            df["EMA20"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
            df["EMA50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
            df["SMA200"] = ta.trend.SMAIndicator(df["close"], window=200).sma_indicator()
            
            # MACD
            macd = ta.trend.MACD(df["close"])
            df["MACD"] = macd.macd()
            df["MACD_Signal"] = macd.macd_signal()
            df["MACD_Diff"] = macd.macd_diff()
            
            # Momentum
            df["RSI"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
            stoch = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"], window=14, smooth_window=3)
            df["Stoch_K"] = stoch.stoch()
            df["Stoch_D"] = stoch.stoch_signal()
            
            # Volatility
            df["ATR"] = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range()
            bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
            df["BB_Upper"] = bb.bollinger_hband()
            df["BB_Middle"] = bb.bollinger_mavg()
            df["BB_Lower"] = bb.bollinger_lband()
            
            logger.info("Technical indicators calculated successfully")
            return df
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            raise
    
    def calculate_support_resistance(self, df: pd.DataFrame, lookback: int = 20) -> Tuple[float, float]:
        """Calculate support and resistance levels"""
        recent_data = df.tail(lookback)
        support = recent_data["low"].min()
        resistance = recent_data["high"].max()
        return support, resistance
    
    def calculate_position_size(self, account_balance: float, stop_loss_pips: float) -> float:
        """Calculate position size based on risk management"""
        risk_amount = account_balance * (self.config.RISK_PERCENTAGE / 100)
        position_size = risk_amount / (stop_loss_pips * 0.01)  # XAU_USD pip value
        return round(position_size, 2)
    
    def calculate_targets(self, price: float, atr: float) -> Dict[str, float]:
        """Calculate scalp and runner targets"""
        return {
            "scalp_target": price - (0.5 * atr),
            "runner_target": price + (1.5 * atr),
            "stop_loss": price + (2.0 * atr),
            "take_profit_1": price - (0.75 * atr),
            "take_profit_2": price - (1.5 * atr)
        }
    
    def generate_signal(self, df: pd.DataFrame) -> Dict[str, any]:
        """Generate trading signal based on multiple indicators"""
        latest = df.iloc[-1]
        
        # Signal conditions
        ema_bullish = latest["EMA20"] > latest["EMA50"] > latest["SMA200"]
        macd_bullish = latest["MACD"] > latest["MACD_Signal"]
        rsi_overbought = latest["RSI"] > 70
        rsi_oversold = latest["RSI"] < 30
        stoch_bullish = latest["Stoch_K"] > latest["Stoch_D"]
        
        signal = {
            "timestamp": datetime.now(),
            "price": latest["close"],
            "ema_bullish": ema_bullish,
            "macd_bullish": macd_bullish,
            "rsi_value": latest["RSI"],
            "rsi_oversold": rsi_oversold,
            "stoch_bullish": stoch_bullish,
            "atr": latest["ATR"],
            "support": self.calculate_support_resistance(df)[0],
            "resistance": self.calculate_support_resistance(df)[1]
        }
        
        # Determine action
        bullish_signals = sum([ema_bullish, macd_bullish, stoch_bullish])
        signal["action"] = "BUY" if bullish_signals >= 2 and rsi_oversold else ("SELL" if bullish_signals <= 1 and rsi_overbought else "HOLD")
        signal["signal_strength"] = bullish_signals / 3 * 100
        
        return signal
    
    def execution_blueprint(self, signal: Dict, targets: Dict) -> None:
        """Print execution blueprint"""
        print("\n" + "="*60)
        print("📊 DZIDZA GOLD BOT - EXECUTION BLUEPRINT")
        print("="*60)
        print(f"⏰ Timestamp: {signal['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"💰 Live Price: ${signal['price']:.2f}")
        print(f"📈 Action: {signal['action']} (Signal Strength: {signal['signal_strength']:.1f}%)")
        print("-"*60)
        print("TECHNICAL ANALYSIS:")
        print(f"  • EMA Trend: {'BULLISH ↑' if signal['ema_bullish'] else 'BEARISH ↓'}")
        print(f"  • MACD: {'BULLISH ↑' if signal['macd_bullish'] else 'BEARISH ↓'}")
        print(f"  • RSI: {signal['rsi_value']:.2f} {'OVERSOLD 🔴' if signal['rsi_oversold'] else 'OVERBOUGHT 🔴' if signal['rsi_value'] > 70 else 'NEUTRAL'}")
        print(f"  • Stochastic: {'BULLISH ↑' if signal['stoch_bullish'] else 'BEARISH ↓'}")
        print(f"  • ATR (Volatility): {signal['atr']:.2f}")
        print("-"*60)
        print("LEVELS:")
        print(f"  • Support: ${signal['support']:.2f}")
        print(f"  • Resistance: ${signal['resistance']:.2f}")
        print("-"*60)
        print("TARGETS:")
        print(f"  • Scalp Target: ${targets['scalp_target']:.2f}")
        print(f"  • Take Profit 1: ${targets['take_profit_1']:.2f}")
        print(f"  • Take Profit 2: ${targets['take_profit_2']:.2f}")
        print(f"  • Runner Target: ${targets['runner_target']:.2f}")
        print(f"  • Stop Loss: ${targets['stop_loss']:.2f}")
        print("="*60 + "\n")
        
        # Log to file
        self.trade_history.append({
            "timestamp": signal["timestamp"],
            "price": signal["price"],
            "action": signal["action"],
            "signal_strength": signal["signal_strength"],
            "targets": targets
        })
    
    def run(self) -> None:
        """Main execution loop"""
        try:
            logger.info("Starting Dzidza Gold Bot...")
            
            df = self.fetch_gold_data()
            if df is None or len(df) < 50:
                logger.error("Insufficient data fetched")
                return
            
            df = self.apply_indicators(df)
            signal = self.generate_signal(df)
            targets = self.calculate_targets(signal["price"], signal["atr"])
            
            self.execution_blueprint(signal, targets)
            logger.info(f"Signal generated: {signal['action']}")
            
        except Exception as e:
            logger.error(f"Bot execution failed: {e}", exc_info=True)

if __name__ == "__main__":
    bot = GoldTradingBot()
    bot.run()