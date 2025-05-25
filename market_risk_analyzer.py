import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from ib_insync import IB, Stock, util

# Risk analizi için kullanılacak ETF'ler ve endeksler
RISK_INDICATORS = {
    "RISK_ON": ["SPY", "IWM", "HYG", "KRE"],  # Risk iştahının arttığı durumlarda yükselen
    "RISK_OFF": ["TLT", "VXX"]                # Güvenli liman arandığında yükselen
}

def connect_to_ibkr():
    """IBKR'ye bağlanır"""
    print("IBKR bağlantısı kuruluyor...")
    ib = IB()
    
    # TWS ve Gateway portlarını dene, öncelik TWS'de olsun
    ports = [7496, 4001]  # TWS ve Gateway portları
    connected = False
    
    for port in ports:
        try:
            service_name = "TWS" if port == 7496 else "Gateway"
            print(f"{service_name} ({port}) bağlantı deneniyor...")
            
            ib.connect('127.0.0.1', port, clientId=2, readonly=True, timeout=20)
            connected = True
            print(f"{service_name} ({port}) ile bağlantı başarılı!")
            break
        except Exception as e:
            print(f"{service_name} ({port}) bağlantı hatası: {e}")
    
    if not connected:
        print("IBKR bağlantısı kurulamadı! TWS veya Gateway çalışıyor mu?")
        return None
    
    return ib

def get_historical_data(ib, symbols, duration="15 D", bar_size="1 day"):
    """
    Sembollerin geçmiş fiyat verilerini alır
    duration: "2 D", "5 D", "15 D" etc.
    bar_size: "1 day", "1 hour", etc.
    """
    all_data = {}
    
    for symbol in symbols:
        try:
            print(f"{symbol} için veri çekiliyor...")
            contract = Stock(symbol, 'SMART', 'USD')
            
            # Kontratı doğrula
            qualified_contracts = ib.qualifyContracts(contract)
            if not qualified_contracts:
                print(f"⚠️ {symbol} için kontrat bulunamadı, atlanıyor")
                continue
                
            contract = qualified_contracts[0]
            
            # Tarihsel veriyi çek
            bars = ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow='TRADES',
                useRTH=True
            )
            
            # DataFrame'e dönüştür
            df = util.df(bars)
            if len(df) > 0:
                all_data[symbol] = df
                print(f"✅ {symbol}: {len(df)} gün veri alındı")
            else:
                print(f"⚠️ {symbol} için veri alınamadı")
                
            # API hız limiti aşılmasın diye kısa bekleme
            ib.sleep(1)
                
        except Exception as e:
            print(f"❌ {symbol} veri çekme hatası: {e}")
    
    return all_data

def calculate_price_changes(market_data):
    """
    Fiyat değişim yüzdelerini hesaplar
    2 günlük, 5 günlük ve 15 günlük değişimler
    """
    changes = {}
    periods = [2, 5, 15]  # 2, 5, 15 günlük değişimler
    
    for symbol, df in market_data.items():
        changes[symbol] = {}
        if len(df) < 2:
            print(f"⚠️ {symbol} için yeterli veri yok, değişim hesaplanamadı")
            continue
            
        # Tersine çevir (en son tarih son sırada olsun)
        df = df.sort_index()
        
        for period in periods:
            # Eğer yeterli veri yoksa, mevcut maksimum veriyi kullan
            available_period = min(period, len(df)-1)
            if available_period < period:
                print(f"⚠️ {symbol} için {period} günlük veri yerine {available_period} günlük veri kullanıldı")
                
            if available_period > 0:
                price_change = (df['close'].iloc[-1] / df['close'].iloc[-available_period-1] - 1) * 100
                changes[symbol][period] = price_change
    
    return changes

def analyze_market_conditions(price_changes):
    """
    Fiyat değişimlerine göre piyasa koşullarını analiz eder
    Risk-on ve Risk-off ağırlıklarını hesaplar
    """
    if not price_changes or len(price_changes) == 0:
        print("⚠️ Piyasa analizi için veri yok!")
        return {'solidity_weight': 2.5, 'yield_weight': 600, 'adv_weight': 0.00025}
    
    # Dönemler için ağırlıklar (yakın dönem daha önemli)
    period_weights = {2: 0.5, 5: 0.3, 15: 0.2}
    periods = list(period_weights.keys())
    
    # Risk-on ve Risk-off skorlarını hesapla
    risk_scores = {
        "RISK_ON": 0,
        "RISK_OFF": 0
    }
    
    valid_indicators = {
        "RISK_ON": [],
        "RISK_OFF": []
    }
    
    # Tüm göstergeler ve dönemler için değişimleri hesapla
    for risk_type, symbols in RISK_INDICATORS.items():
        for symbol in symbols:
            if symbol in price_changes:
                valid_indicators[risk_type].append(symbol)
                
                # Tüm dönemler için ağırlıklı değişimi hesapla
                weighted_change = 0
                for period in periods:
                    if period in price_changes[symbol]:
                        weighted_change += price_changes[symbol][period] * period_weights[period]
                
                # Risk tipine göre skora ekle
                risk_scores[risk_type] += weighted_change
    
    # Geçerli gösterge sayısına göre ortalamaları al
    for risk_type in risk_scores:
        if len(valid_indicators[risk_type]) > 0:
            risk_scores[risk_type] /= len(valid_indicators[risk_type])
    
    # Risk dengesini hesapla (Risk-on - Risk-off)
    risk_balance = risk_scores["RISK_ON"] - risk_scores["RISK_OFF"]
    
    # Normalize et (-10 ile +10 arasında sınırla)
    norm_risk_balance = max(min(risk_balance, 10), -10) / 10  # -1 ile 1 arasında
    
    # Baz ağırlıklar
    base_solidity = 2.5
    base_yield = 600
    base_adv = 0.00025
    
    # Değişim faktörü (en fazla %50 artış/azalış)
    change_factor = norm_risk_balance * 0.5  # -0.5 ile 0.5 arasında
    
    # Ağırlıkları hesapla
    # Risk-on (pozitif denge): Solidity azalt, Yield artır, ADV artır
    # Risk-off (negatif denge): Solidity artır, Yield azalt, ADV azalt
    solidity_weight = base_solidity * (1 - change_factor)  # 1.25 ile 3.75 arasında
    yield_weight = base_yield * (1 + change_factor)        # 300 ile 900 arasında
    
    # ADV için yüksek piyasa riskinde (risk-off) düşük ağırlık, 
    # düşük piyasa riskinde (risk-on) yüksek ağırlık uygula
    adv_weight = base_adv * (1 + change_factor * 0.7)  # Değişim oranını %70 ile sınırla
    
    return {
        'solidity_weight': round(solidity_weight, 2),
        'yield_weight': round(yield_weight, 2),
        'adv_weight': round(adv_weight, 8),
        'risk_balance': round(risk_balance, 2),
        'risk_on_score': round(risk_scores["RISK_ON"], 2),
        'risk_off_score': round(risk_scores["RISK_OFF"], 2)
    }

def generate_market_report(price_changes, market_weights):
    """Piyasa koşulları hakkında detaylı rapor üretir"""
    periods = [2, 5, 15]
    
    print("\n=== PAZAR KOŞULLARI RAPORU ===")
    
    # Değişimleri göster
    print("\nFiyat Değişimleri (%):")
    print(f"{'Sembol':<8}", end="")
    for period in periods:
        print(f"{period:>5} gün", end="  ")
    print("")
    
    # Tüm sembolleri toplu göster
    all_symbols = set()
    for symbols in RISK_INDICATORS.values():
        all_symbols.update(symbols)
    all_symbols = sorted(all_symbols)
    
    for symbol in all_symbols:
        if symbol in price_changes:
            print(f"{symbol:<8}", end="")
            for period in periods:
                if period in price_changes[symbol]:
                    print(f"{price_changes[symbol][period]:>7.2f}", end="  ")
                else:
                    print(f"{'N/A':>7}", end="  ")
            print("")
    
    # Risk durumunu göster
    print("\nRisk Durumu:")
    print(f"Risk-On Skoru: {market_weights['risk_on_score']:.2f}")
    print(f"Risk-Off Skoru: {market_weights['risk_off_score']:.2f}")
    print(f"Risk Dengesi: {market_weights['risk_balance']:.2f}")
    
    # Stratejiyi açıkla
    if market_weights['risk_balance'] > 3:
        risk_state = "📈 GÜÇLÜ RİSK-ON (Yüksek risk iştahı)"
        strategy = "Getiri (CUR_YIELD) ve işlem hacmi (ADV) odaklı hisselere ağırlık ver"
    elif market_weights['risk_balance'] > 0:
        risk_state = "🔼 HAFİF RİSK-ON (Risk iştahı var)"
        strategy = "Getiri ve işlem hacmi biraz daha önemli, dengeli gitmeye çalış"
    elif market_weights['risk_balance'] > -3:
        risk_state = "🔽 HAFİF RİSK-OFF (Risk iştahı düşük)"
        strategy = "Sağlamlık (SOLIDITY) biraz daha önemli, kaliteli hisseler seç"
    else:
        risk_state = "📉 GÜÇLÜ RİSK-OFF (Güvenli limanlara kaçış)"
        strategy = "Sağlamlık odaklı hisselere ağırlık ver, işlem hacmini göz ardı et"
    
    print(f"\nPazar Durumu: {risk_state}")
    print(f"Strateji: {strategy}")
    print(f"\nKullanılacak Ağırlıklar:")
    print(f"Solidity Ağırlık: {market_weights['solidity_weight']:.2f} (Baz: 2.50)")
    print(f"Yield Ağırlık: {market_weights['yield_weight']:.2f} (Baz: 600.00)")
    print(f"ADV Ağırlık: {market_weights['adv_weight']:.8f} (Baz: 0.00025000)")
    
    # Kullanılacak değişim oranlarını göster
    print(f"\nSolidity Değişim: %{((market_weights['solidity_weight']/2.5 - 1) * 100):.1f}")
    print(f"Yield Değişim: %{((market_weights['yield_weight']/600 - 1) * 100):.1f}")
    print(f"ADV Değişim: %{((market_weights['adv_weight']/0.00025 - 1) * 100):.1f}")

def save_market_weights(market_weights):
    """Piyasa ağırlıklarını dosyaya kaydeder"""
    try:
        # Mevcut tarihi ekle
        market_weights['date'] = datetime.now().strftime('%Y-%m-%d')
        
        # Pandas DataFrame'e dönüştür ve kaydet
        df = pd.DataFrame([market_weights])
        df.to_csv('market_weights.csv', index=False)
        print("\nPiyasa ağırlıkları 'market_weights.csv' dosyasına kaydedildi.")
        
        return True
    except Exception as e:
        print(f"Piyasa ağırlıkları kaydedilirken hata: {e}")
        return False

def get_saved_market_weights():
    """Kaydedilmiş piyasa ağırlıklarını yükler"""
    try:
        if os.path.exists('market_weights.csv'):
            df = pd.read_csv('market_weights.csv')
            if len(df) > 0:
                # Bugünün tarihi mi kontrol et
                today = datetime.now().strftime('%Y-%m-%d')
                if 'date' in df.columns and df['date'].iloc[0] == today:
                    weights = {
                        'solidity_weight': df['solidity_weight'].iloc[0],
                        'yield_weight': df['yield_weight'].iloc[0],
                        'adv_weight': df['adv_weight'].iloc[0] if 'adv_weight' in df.columns else 0.00025,
                        'risk_balance': df['risk_balance'].iloc[0] if 'risk_balance' in df.columns else 0,
                        'risk_on_score': df['risk_on_score'].iloc[0] if 'risk_on_score' in df.columns else 0,
                        'risk_off_score': df['risk_off_score'].iloc[0] if 'risk_off_score' in df.columns else 0
                    }
                    print(f"\nBugünün piyasa ağırlıkları yüklendi:")
                    print(f"Solidity: {weights['solidity_weight']:.2f}, Yield: {weights['yield_weight']:.2f}, ADV: {weights['adv_weight']:.8f}")
                    return weights
                
    except Exception as e:
        print(f"Kaydedilmiş ağırlıkları yüklerken hata: {e}")
    
    return None

def main():
    """Ana program"""
    print("Piyasa Risk Analizi Başlatılıyor...")
    
    # Önce kaydedilmiş ağırlıkları kontrol et
    saved_weights = get_saved_market_weights()
    if saved_weights:
        user_input = input("Bugün için piyasa analizi zaten yapılmış. Yeniden analiz yapmak ister misiniz? (e/h): ")
        if user_input.lower() not in ['e', 'evet', 'y', 'yes']:
            print("Mevcut piyasa ağırlıkları kullanılacak.")
            generate_market_report(None, saved_weights)
            return saved_weights
    
    # IBKR'ye bağlan
    ib = connect_to_ibkr()
    if ib is None:
        print("IBKR bağlantısı kurulamadı!")
        return {'solidity_weight': 2.5, 'yield_weight': 600, 'adv_weight': 0.00025}
    
    try:
        # Tüm sembolleri topla
        all_symbols = []
        for symbols in RISK_INDICATORS.values():
            all_symbols.extend(symbols)
        
        # Verileri çek
        market_data = get_historical_data(ib, all_symbols, duration="20 D", bar_size="1 day")
        
        # Değişimleri hesapla
        price_changes = calculate_price_changes(market_data)
        
        # Piyasa koşullarını analiz et
        market_weights = analyze_market_conditions(price_changes)
        
        # Rapor oluştur
        generate_market_report(price_changes, market_weights)
        
        # Ağırlıkları kaydet
        save_market_weights(market_weights)
        
        return market_weights
        
    except Exception as e:
        print(f"Piyasa analizi sırasında hata: {e}")
        import traceback
        traceback.print_exc()
        return {'solidity_weight': 2.5, 'yield_weight': 600, 'adv_weight': 0.00025}
        
    finally:
        # IBKR bağlantısını kapat
        if ib and ib.isConnected():
            ib.disconnect()
            print("\nIBKR bağlantısı kapatıldı")

if __name__ == "__main__":
    main() 