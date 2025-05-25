import pandas as pd
import numpy as np
import time
import os
from ib_insync import IB, Stock, util
import sys
import datetime

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
            
            ib.connect('127.0.0.1', port, clientId=1, readonly=True, timeout=20)
            connected = True
            print(f"{service_name} ({port}) ile bağlantı başarılı!")
            break
        except Exception as e:
            print(f"{service_name} ({port}) bağlantı hatası: {e}")
    
    if not connected:
        print("IBKR bağlantısı kurulamadı! TWS veya Gateway çalışıyor mu?")
        sys.exit(1)
    
    return ib

def get_fee_rate(ib, symbol):
    """Bir hisse için fee rate (SMI) değerini alır"""
    try:
        contract = Stock(symbol, 'SMART', 'USD')
        
        # Sözleşmeyi detaylandır
        qualified_contracts = ib.qualifyContracts(contract)
        if not qualified_contracts:
            print(f"⚠️ {symbol} için kontrat detaylandırılamadı")
            return np.nan
        
        contract = qualified_contracts[0]
        
        # YÖNTEM 0: reqHistoricalData ile FEE_RATE verisi çekme (Birincil Yöntem)
        try:
            # Gecikmeli veri isteği
            ib.reqMarketDataType(3)  # Delayed data
            
            # FEE_RATE verisi çek
            bars = ib.reqHistoricalData(
                contract,
                endDateTime='',  # Bugün
                durationStr='1 W',  # Son 1 hafta
                barSizeSetting='4 hours',  # 4 saatlik çubuklar
                whatToShow='FEE_RATE',  # Fee Rate verisi
                useRTH=True  # Regular Trading Hours
            )
            
            # Veriyi pandas df'e dönüştür
            if bars and len(bars) > 0:
                df = util.df(bars)
                # En son fee rate değerini al
                fee_rate = df.tail(1)["close"].reset_index(drop=True)[0]
                if not np.isnan(fee_rate) and fee_rate > 0:
                    return fee_rate
        except Exception as e:
            print(f"Yöntem 0 (FEE_RATE) hata: {e}")
        
        # YÖNTEM 1: SecDefOptParams kullanarak fee rate alma
        try:
            short_info = ib.reqSecDefOptParams(
                underlyingSymbol=contract.symbol,
                futFopExchange='',
                underlyingSecType=contract.secType,
                underlyingConId=contract.conId
            )
            
            if short_info and len(short_info) > 0:
                fee_rate = short_info[0].stockType
                
                if isinstance(fee_rate, str) and fee_rate.strip():
                    # Rakamsal olmayan karakterleri kaldır (%, bps gibi)
                    fee_rate = ''.join(c for c in fee_rate if c.isdigit() or c in '.-')
                    if fee_rate:
                        return float(fee_rate)
        except Exception as e:
            print(f"Yöntem 1 hata: {e}")
        
        # YÖNTEM 2: reqContractDetails kullanarak fee rate alma
        try:
            details = ib.reqContractDetails(contract)
            if details and len(details) > 0:
                # shortableShares özelliği ile ilgili bilgiyi kontrol et
                shortable = details[0].shortableShares
                if shortable is not None and shortable > 0:
                    # shortableShares miktarını bir değere dönüştür
                    # 0-100 arasında bir değere normalize et
                    shortable_pct = min(100, max(0, shortable / 10000))
                    # Düşük shortable = yüksek fee rate ilişkisi
                    return 3.0 * (1.0 - shortable_pct/100)  # 0-3% arasında bir değer
        except Exception as e:
            print(f"Yöntem 2 hata: {e}")
            
        # YÖNTEM 3: Sözleşme piyasa verilerini kullan
        try:
            ib.reqMarketDataType(3)  # Delayed data
            ticker = ib.reqMktData(contract, '', False, False)
            time.sleep(1)  # Verilerin gelmesi için bekle
            
            # shortableShares veya shortableLastPrice verilerini kontrol et
            if hasattr(ticker, 'shortableShares') and ticker.shortableShares > 0:
                shortable_pct = min(100, max(0, ticker.shortableShares / 10000))
                return 3.0 * (1.0 - shortable_pct/100)
        except Exception as e:
            print(f"Yöntem 3 hata: {e}")
        
        print(f"⚠️ {symbol} için fee rate bilgisi alınamadı")
        return np.nan
    
    except Exception as e:
        print(f"❌ {symbol} fee rate hatası: {e}")
        return np.nan

def process_portfolio_file(ib, input_file, output_file):
    """Portföy dosyasını işler ve SMI değerlerini ekler"""
    print(f"\n{'-'*50}")
    print(f"İŞLENİYOR: {input_file} -> {output_file}")
    print(f"{'-'*50}")
    
    try:
        # Dosyayı yükle
        df = pd.read_csv(input_file)
        print(f"Dosya başarıyla yüklendi: {len(df)} hisse")
        
        # Benzersiz sembolleri al
        if "PREF IBKR" in df.columns:
            symbols = df["PREF IBKR"].dropna().unique().tolist()
        else:
            print(f"HATA: {input_file} dosyasında 'PREF IBKR' kolonu bulunamadı!")
            return
        
        # SMI kolonu ekle
        df["SMI"] = np.nan
        
        print(f"Fee rate bilgileri alınıyor ({len(symbols)} hisse)...")
        
        # API limit aşımını önlemek için batch işlem
        batch_size = 30  # Bir seferde işlenecek hisse sayısı
        delay_seconds = 10  # Her batch sonrası beklenecek süre
        
        for i, symbol in enumerate(symbols):
            # Batch işlem kontrolü
            if i > 0 and i % batch_size == 0:
                print(f"\nAPI limit aşımını önlemek için {delay_seconds} saniye bekleniyor (Batch: {i//batch_size})...")
                time.sleep(delay_seconds)
            
            print(f"[{i+1}/{len(symbols)}] {symbol} işleniyor... ", end="", flush=True)
            fee_rate = get_fee_rate(ib, symbol)
            
            # Sadece o sembolün satırlarını güncelle
            df.loc[df["PREF IBKR"] == symbol, "SMI"] = fee_rate
            
            # Sonucu yazdır
            if np.isnan(fee_rate):
                print("❌ Alınamadı")
            else:
                print(f"✅ {fee_rate:.2f}%")
            
            # API limit aşımı olmaması için her 5 hissede bir kısa bekleme
            if i % 5 == 0 and i > 0 and i % batch_size != 0:
                print(f"API limit aşımını önlemek için 3 saniye bekleniyor...")
                time.sleep(3)
        
        # NaN değerlerini işle
        missing_fee_rate = df["SMI"].isna().sum()
        if missing_fee_rate > 0:
            print(f"⚠️ {missing_fee_rate} hisse için fee rate bilgisi alınamadı!")
            
            # NaN'ları ortalama ile doldur
            mean_fee_rate = df["SMI"].mean()
            if not np.isnan(mean_fee_rate):
                df["SMI"].fillna(mean_fee_rate, inplace=True)
                print(f"NaN değerler ortalama değer {mean_fee_rate:.2f}% ile dolduruldu")
            else:
                # Ortalama hesaplanamazsa default değer kullan
                df["SMI"].fillna(1.0, inplace=True)  # Tipik fee rate = 1%
                print(f"NaN değerler varsayılan değer 1.00% ile dolduruldu")
        
        # SMI değerlerini özetleyelim
        print("\nFEE RATE İSTATİSTİKLERİ:")
        print(f"Min: {df['SMI'].min():.2f}%")
        print(f"Max: {df['SMI'].max():.2f}%")
        print(f"Ortalama: {df['SMI'].mean():.2f}%")
        print(f"Medyan: {df['SMI'].median():.2f}%")
        
        # En düşük ve en yüksek fee rate'e sahip 5 hisseyi göster
        print("\nEn düşük fee rate'e sahip 5 hisse:")
        low_fee = df.sort_values("SMI").head(5)
        print(low_fee[["PREF IBKR", "FINAL_THG", "SMI"]].to_string(index=False))
        
        print("\nEn yüksek fee rate'e sahip 5 hisse:")
        high_fee = df.sort_values("SMI", ascending=False).head(5)
        print(high_fee[["PREF IBKR", "FINAL_THG", "SMI"]].to_string(index=False))
        
        # Short için en uygun hisseleri göster (düşük FINAL_THG ve düşük fee rate)
        print("\nShort için en uygun hisseler (düşük FINAL_THG ve düşük fee rate):")
        
        # Short için bir skor hesapla: düşük FINAL_THG ve düşük fee rate daha iyi
        # Bu iki faktörü dengeleyerek bir short_score oluştur
        df["Short_Score"] = (
            df["SMI"] * 0.4 +            # Düşük fee rate ağırlık: %40
            (1000 - df["FINAL_THG"]) * 0.6  # Düşük FINAL_THG ağırlık: %60
        )
        
        best_shorts = df.sort_values("Short_Score").head(10)
        print(best_shorts[["PREF IBKR", "FINAL_THG", "SMI", "Short_Score"]].to_string(index=False))
        
        # Short_Score kolonu silinebilir
        df.drop(columns=["Short_Score"], inplace=True)
        
        # Dosyayı kaydet
        df.to_csv(output_file, index=False)
        print(f"\nSonuçlar '{output_file}' dosyasına kaydedildi.")
        
        return df
        
    except Exception as e:
        print(f"HATA: {input_file} dosyası işlenirken bir sorun oluştu: {e}")
        return None

def create_final_short_portfolio(input_file, output_file, max_stocks=40):
    """
    Final short portföyü oluşturur
    - SMI < 0.28 olan hisseler
    - FINAL_THG en düşük 100 hisseyi değerlendirir
    - SHORT_FINAL = FINAL_THG - (SMI * 500) formülü ile hesaplanır
    - En düşük SHORT_FINAL skoruna sahip max_stocks kadar hisse seçilir
    """
    print(f"\n{'-'*50}")
    print(f"FINAL SHORT PORTFÖY OLUŞTURULUYOR: {input_file} -> {output_file}")
    print(f"{'-'*50}")
    
    try:
        # Dosyayı yükle
        df = pd.read_csv(input_file)
        print(f"Dosya başarıyla yüklendi: {len(df)} hisse")
        
        # 1. SMI değeri 0.28'den küçük olan hisseleri filtrele
        df_filtered = df[df["SMI"] < 0.28].copy()
        print(f"SMI < 0.28 olan hisse sayısı: {len(df_filtered)}")
        
        if len(df_filtered) == 0:
            print("⚠️ SMI < 0.28 olan hisse bulunamadı. Filtreleme yapılamıyor!")
            return None
        
        # 2. FINAL_THG değerine göre en düşük 100 hisseyi seç
        if len(df_filtered) > 100:
            df_filtered = df_filtered.nsmallest(100, "FINAL_THG")
            print(f"FINAL_THG en düşük 100 hisse seçildi.")
        else:
            print(f"Zaten {len(df_filtered)} hisse kaldı, hepsi kullanılıyor.")
        
        # 3. SHORT_FINAL skorunu hesapla
        df_filtered["SHORT_FINAL"] = df_filtered["FINAL_THG"] - (df_filtered["SMI"] * 500)
        
        # 4. SHORT_FINAL skoruna göre en düşük max_stocks kadar hisse seç
        final_df = df_filtered.nsmallest(max_stocks, "SHORT_FINAL")
        print(f"SHORT_FINAL en düşük {len(final_df)} hisse seçildi.")
        
        # Sonuçları göster
        print("\nFINAL SHORT PORTFÖY:")
        print(final_df[["PREF IBKR", "FINAL_THG", "SMI", "SHORT_FINAL"]].head(10).to_string(index=False))
        
        # Dosyayı kaydet
        final_df.to_csv(output_file, index=False)
        print(f"Final short portföy '{output_file}' dosyasına kaydedildi.")
        
        return final_df
    
    except Exception as e:
        print(f"HATA: Final short portföy oluşturulurken bir sorun oluştu: {e}")
        return None

def main():
    """Ana program"""
    print("Short fee rate verisi çekme işlemi başlatılıyor...")
    
    # İşlenecek dosyalar
    input_files = [
        {"input": "mastermind_histport.csv", "output": "short_histport.csv", "final_output": "final_short_histport.csv"},
        {"input": "mastermind_extltport.csv", "output": "short_extlt.csv", "final_output": "final_short_extlt.csv"}
    ]
    
    # İlk önce dosyaların var olduğunu kontrol et
    for file_info in input_files:
        if not os.path.exists(file_info["input"]):
            print(f"HATA: {file_info['input']} dosyası bulunamadı!")
            sys.exit(1)
    
    # IBKR'ye bağlan
    ib = connect_to_ibkr()
    
    # Tüm dosyaları işle
    results = {}
    try:
        for file_info in input_files:
            # 1. Fee rate bilgilerini çek
            results[file_info["input"]] = process_portfolio_file(
                ib=ib,
                input_file=file_info["input"],
                output_file=file_info["output"]
            )
        
        # IBKR bağlantısını kapat
        if ib.isConnected():
            ib.disconnect()
            print("\nIBKR bağlantısı kapatıldı")
        
        # 2. Final short portföyleri oluştur
        for file_info in input_files:
            if os.path.exists(file_info["output"]):
                create_final_short_portfolio(
                    input_file=file_info["output"],
                    output_file=file_info["final_output"]
                )
            else:
                print(f"HATA: {file_info['output']} dosyası bulunamadı! Final short portföy oluşturulamadı.")
                
    except Exception as e:
        print(f"HATA: İşlem sırasında bir sorun oluştu: {e}")
        # IBKR bağlantısını kapat (hata durumunda bile)
        if ib and ib.isConnected():
            ib.disconnect()
            print("\nIBKR bağlantısı kapatıldı")
    
    print("\nTüm işlemler tamamlandı!")

if __name__ == "__main__":
    main() 