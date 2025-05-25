import pandas as pd
import numpy as np
import os
import time
from datetime import datetime, timedelta
from ib_insync import IB, Stock, Contract, util
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.cluster import KMeans, AgglomerativeClustering
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.decomposition import PCA
from sklearn.metrics.pairwise import cosine_similarity
from scipy.cluster.hierarchy import dendrogram, linkage
from tqdm import tqdm
import warnings
# Deep learning kütüphaneleri
try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential, Model
    from tensorflow.keras.layers import Dense, LSTM, RepeatVector, TimeDistributed, Input, Dropout
    from tensorflow.keras.optimizers import Adam
    from tensorflow.keras.callbacks import EarlyStopping
    HAVE_TENSORFLOW = True
except ImportError:
    print("TensorFlow kurulu değil, basit yöntemler kullanılacak")
    HAVE_TENSORFLOW = False

warnings.filterwarnings('ignore')

# ETF listesi
ETFS = ["TLT", "IEF", "SHY", "SPY", "KRE", "IWM", "HYG", "PFF", "PGF", "PGX"]

class MastermindAnalysis:
    def __init__(self):
        self.ib = None
        self.pref_symbols = []
        self.hist_symbols = []    # historical_data.csv'den gelen semboller
        self.extlt_symbols = []   # extlthistorical.csv'den gelen semboller
        self.historical_data = {}  # Sembol: DataFrame pairs
        self.etf_data = {}        # ETF: DataFrame pairs
        self.correlation_data = None
        self.similarity_matrix_hist = None
        self.similarity_matrix_extlt = None
        self.groups_hist = {}     # historical_data.csv için gruplar
        self.groups_extlt = {}    # extlthistorical.csv için gruplar
        self.n_groups = 12        # Oluşturulacak grup sayısı
        self.lstm_encodings = {}  # LSTM tabanlı kodlamalar (hisselerin davranış parmak izleri)
        self.optimal_weights = None  # Otomatik bulunan optimal ağırlıklar
        
    def connect_to_ibkr(self):
        """IBKR'ye bağlan"""
        print("IBKR bağlantısı kuruluyor...")
        self.ib = IB()
        
        # TWS ve Gateway portlarını dene, öncelik TWS'de olsun
        ports = [7496, 4001]  # TWS ve Gateway portları
        connected = False
        
        for port in ports:
            try:
                service_name = "TWS" if port == 7496 else "Gateway"
                print(f"{service_name} ({port}) bağlantı deneniyor...")
                
                self.ib.connect('127.0.0.1', port, clientId=1, readonly=True, timeout=20)
                connected = True
                print(f"{service_name} ({port}) ile bağlantı başarılı!")
                break
            except Exception as e:
                print(f"{service_name} ({port}) bağlantı hatası: {e}")
        
        if not connected:
            raise Exception("IBKR bağlantısı kurulamadı! TWS veya Gateway çalışıyor mu?")
        
        return connected
    
    def disconnect_from_ibkr(self):
        """IBKR bağlantısını kapat"""
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()
            print("IBKR bağlantısı kapatıldı")
    
    def load_symbols_from_csv(self):
        """CSV dosyalarından sembolleri yükle - Her dosya için ayrı sembol listeleri oluştur"""
        print("CSV dosyalarından preferred hisse sembollerini yükleniyor...")
        hist_symbols = set()
        extlt_symbols = set()
        
        # historical_data.csv'den sembolleri oku
        if os.path.exists("historical_data.csv"):
            df_hist = pd.read_csv("historical_data.csv")
            if "PREF IBKR" in df_hist.columns:
                hist_symbols.update(df_hist["PREF IBKR"].dropna().unique())
                print(f"historical_data.csv'den {len(df_hist['PREF IBKR'].dropna().unique())} sembol yüklendi")
            else:
                print("historical_data.csv dosyasında 'PREF IBKR' kolonu bulunamadı")
        else:
            print("historical_data.csv dosyası bulunamadı")
        
        # extlthistorical.csv'den sembolleri oku
        if os.path.exists("extlthistorical.csv"):
            df_extlt = pd.read_csv("extlthistorical.csv")
            if "PREF IBKR" in df_extlt.columns:
                extlt_symbols.update(df_extlt["PREF IBKR"].dropna().unique())
                print(f"extlthistorical.csv'den {len(df_extlt['PREF IBKR'].dropna().unique())} sembol yüklendi")
            else:
                print("extlthistorical.csv dosyasında 'PREF IBKR' kolonu bulunamadı")
        else:
            print("extlthistorical.csv dosyası bulunamadı")
        
        # Tüm sembolleri birleştir
        all_symbols = hist_symbols.union(extlt_symbols)
        self.pref_symbols = list(all_symbols)
        
        # Dosya bazlı sembol listeleri
        self.hist_symbols = list(hist_symbols)
        self.extlt_symbols = list(extlt_symbols)
        
        print(f"historical_data.csv'den {len(hist_symbols)} sembol, extlthistorical.csv'den {len(extlt_symbols)} sembol")
        print(f"Toplam {len(self.pref_symbols)} benzersiz sembol yüklendi")
        
        return self.pref_symbols
    
    def create_contract(self, symbol, sec_type="STK", exchange="SMART", currency="USD"):
        """Contract nesnesi oluştur"""
        contract = Contract()
        contract.symbol = symbol
        contract.secType = sec_type
        contract.exchange = exchange
        contract.currency = currency
        return contract
    
    def get_historical_data(self, symbol, duration="3 Y", bar_size="1 day"):
        """Belirli bir sembol için tarihsel veri al"""
        contract = self.create_contract(symbol)
        
        # Her denemede daha kısa bir süre dene
        durations = ["3 Y", "2 Y", "1 Y", "6 M"]
        
        for dur in durations:
            try:
                print(f"{symbol} için {dur} tarihsel veri alınıyor...")
                bars = self.ib.reqHistoricalData(
                    contract,
                    endDateTime='',
                    durationStr=dur,
                    barSizeSetting=bar_size,
                    whatToShow='TRADES',
                    useRTH=True,
                    formatDate=1
                )
                
                if bars and len(bars) > 0:
                    print(f"{symbol} için {len(bars)} veri noktası alındı")
                    df = util.df(bars)
                    return df
                
            except Exception as e:
                print(f"{symbol} tarihsel veri hatası ({dur}): {e}")
                self.ib.sleep(1)  # API limit aşımlarına karşı bekle
        
        print(f"{symbol} için veri alınamadı.")
        return pd.DataFrame()  # Boş DataFrame
    
    def fetch_all_historical_data(self):
        """Tüm semboller için tarihsel veri al"""
        print("Tüm preferred hisselerin tarihsel verileri alınıyor...")
        
        # Tarihsel verileri saklamak için dictionary
        self.historical_data = {}
        
        # Preferred hisseler için tarihsel veri al
        for symbol in tqdm(self.pref_symbols, desc="Preferred Hisseler"):
            df = self.get_historical_data(symbol)
            if not df.empty:
                # Tarih sütununu index olarak ayarla
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                
                # Sadece close ve volume sütunlarını sakla
                self.historical_data[symbol] = df[['close', 'volume']]
            
            # API limit aşımlarına karşı bekle
            time.sleep(1)
        
        # ETF'ler için tarihsel veri al
        print("ETF'lerin tarihsel verileri alınıyor...")
        for etf in tqdm(ETFS, desc="ETF'ler"):
            df = self.get_historical_data(etf)
            if not df.empty:
                # Tarih sütununu index olarak ayarla
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                
                # Sadece close sütununu sakla
                self.etf_data[etf] = df[['close']]
            
            # API limit aşımlarına karşı bekle
            time.sleep(1)
        
        print(f"{len(self.historical_data)} preferred hisse ve {len(self.etf_data)} ETF için tarihsel veri alındı")
        
        return self.historical_data, self.etf_data
    
    def save_historical_data(self, output_dir="mastermind_data"):
        """Tarihsel verileri CSV dosyalarına kaydet"""
        # Output dizinini oluştur
        os.makedirs(output_dir, exist_ok=True)
        
        # Preferred hisselerin verilerini kaydet
        for symbol, df in self.historical_data.items():
            output_file = os.path.join(output_dir, f"{symbol}_historical.csv")
            df.to_csv(output_file)
            print(f"{output_file} kaydedildi")
        
        # ETF'lerin verilerini kaydet
        for etf, df in self.etf_data.items():
            output_file = os.path.join(output_dir, f"{etf}_historical.csv")
            df.to_csv(output_file)
            print(f"{output_file} kaydedildi")
        
        print(f"Tüm veriler {output_dir} dizinine kaydedildi")
    
    def load_historical_data(self, input_dir="mastermind_data"):
        """CSV dosyalarından tarihsel verileri yükle"""
        print(f"{input_dir} dizininden tarihsel veriler yükleniyor...")
        
        self.historical_data = {}
        self.etf_data = {}
        
        # Dizin var mı kontrol et
        if not os.path.exists(input_dir):
            print(f"{input_dir} dizini bulunamadı. Lütfen önce verileri çekin ve kaydedin.")
            return False
        
        # Preferred hisse dosyalarını yükle
        for symbol in self.pref_symbols:
            file_path = os.path.join(input_dir, f"{symbol}_historical.csv")
            if os.path.exists(file_path):
                df = pd.read_csv(file_path)
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                
                # 'volume' kolonu yoksa ekle
                if 'volume' not in df.columns:
                    print(f"UYARI: {symbol} için 'volume' kolonu bulunamadı, 0 değerleriyle oluşturuluyor")
                    df['volume'] = 0
                
                self.historical_data[symbol] = df
                print(f"{symbol} verileri yüklendi")
            else:
                print(f"{file_path} bulunamadı, {symbol} atlanıyor")
        
        # ETF dosyalarını yükle
        for etf in ETFS:
            file_path = os.path.join(input_dir, f"{etf}_historical.csv")
            if os.path.exists(file_path):
                df = pd.read_csv(file_path)
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                
                # ETF'lerde volume kolonu yoksa ekle
                if 'volume' not in df.columns:
                    print(f"UYARI: {etf} için 'volume' kolonu bulunamadı, 0 değerleriyle oluşturuluyor")
                    df['volume'] = 0
                
                self.etf_data[etf] = df
                print(f"{etf} verileri yüklendi")
            else:
                print(f"{file_path} bulunamadı, {etf} atlanıyor")
        
        print(f"{len(self.historical_data)} preferred hisse ve {len(self.etf_data)} ETF verisi yüklendi")
        
        return len(self.historical_data) > 0 and len(self.etf_data) > 0
        
    def calculate_returns(self):
        """Tüm hisseler ve ETF'ler için günlük getiri hesapla"""
        print("Günlük getiriler hesaplanıyor...")
        
        # Preferred hisseler için günlük getiri hesapla
        for symbol, df in self.historical_data.items():
            self.historical_data[symbol]['return'] = df['close'].pct_change()
        
        # ETF'ler için günlük getiri hesapla
        for etf, df in self.etf_data.items():
            self.etf_data[etf]['return'] = df['close'].pct_change()
            
        print("Günlük getiriler hesaplandı")
    
    def calculate_correlations_with_etfs(self):
        """Her hissenin ETF'lerle ilişkisini makine öğrenimi teknikleriyle analiz et"""
        print("ETF ilişkileri gelişmiş analiz ile hesaplanıyor...")
        
        correlation_data = []
        
        # Her hisse için ETF'lerle ilişkiyi analiz et
        for symbol, df in self.historical_data.items():
            symbol_data = {'Symbol': symbol}
            
            # Hissenin kaynağını belirle
            source = 'historical_data.csv' if symbol in self.hist_symbols else 'extlthistorical.csv'
            symbol_data['Source'] = source
            
            # Volatilite ve hacim metrikleri
            returns = df['return'].dropna()
            if len(returns) > 10:  # Yeterli veri var mı?
                symbol_data['Volatility'] = returns.std() * np.sqrt(252)  # Yıllık volatilite
                
                # Hacim verisini kontrol et - yoksa varsayılan değer kullan
                if 'volume' in df.columns:
                    symbol_data['Avg_Volume'] = df['volume'].mean()
                else:
                    # 'volume' kolonu yoksa 0 olarak ayarla
                    symbol_data['Avg_Volume'] = 0
                    # Log uyarısı ekle
                    print(f"UYARI: {symbol} için 'volume' verisi bulunamadı, 0 olarak varsayıldı")
                
                # Her ETF için gelişmiş ilişki analizi
                for etf in ETFS:
                    if etf in self.etf_data:
                        etf_returns = self.etf_data[etf]['return'].dropna()
                        
                        # Ortak tarihlerdeki getiriler
                        common_dates = returns.index.intersection(etf_returns.index)
                        
                        if len(common_dates) > 30:  # En az 30 ortak gün
                            # 1. Basit korelasyon
                            corr = returns.loc[common_dates].corr(etf_returns.loc[common_dates])
                            symbol_data[f'Corr_{etf}'] = corr
                            
                            # 2. ETF'nin gecikmeli etkileri (ETF hareketinden sonraki 1-3 gün)
                            lag_effects = []
                            for lag in range(1, 4):  # 1, 2, 3 günlük gecikmeler
                                # ETF t gününde, hisse t+lag gününde
                                paired_data = pd.DataFrame({
                                    'etf': etf_returns.loc[common_dates].values[:-lag] if lag < len(common_dates) else [],
                                    'stock': returns.loc[common_dates].values[lag:] if lag < len(common_dates) else []
                                })
                                
                                if len(paired_data) > 20:  # Yeterli veri var mı
                                    lag_corr = paired_data['etf'].corr(paired_data['stock'])
                                    lag_effects.append(lag_corr)
                                else:
                                    lag_effects.append(0)
                            
                            # Gecikme etkilerinin ortalaması
                            symbol_data[f'Lag_Effect_{etf}'] = np.mean(lag_effects)
                            
                            # 3. Hisse ve ETF hareket yönleri arasındaki ilişki
                            # (Pozitif veya negatif hareketin uyumluluğu)
                            etf_up = etf_returns.loc[common_dates] > 0
                            stock_up = returns.loc[common_dates] > 0
                            direction_match = (etf_up & stock_up) | (~etf_up & ~stock_up)  # Aynı yönde hareket
                            direction_match_ratio = direction_match.mean()  # Yön uyumu oranı
                            symbol_data[f'Direction_Match_{etf}'] = direction_match_ratio
                            
                            # 4. Koşullu ilişki: ETF yükselirken/düşerken hissenin tepkisi
                            etf_up_days = etf_returns.loc[common_dates] > 0
                            etf_down_days = etf_returns.loc[common_dates] < 0
                            
                            if sum(etf_up_days) > 10:
                                up_response = returns.loc[common_dates][etf_up_days].mean() / etf_returns.loc[common_dates][etf_up_days].mean()
                                symbol_data[f'Up_Response_{etf}'] = up_response
                            else:
                                symbol_data[f'Up_Response_{etf}'] = 0
                                
                            if sum(etf_down_days) > 10:
                                down_response = returns.loc[common_dates][etf_down_days].mean() / etf_returns.loc[common_dates][etf_down_days].mean()
                                symbol_data[f'Down_Response_{etf}'] = down_response
                            else:
                                symbol_data[f'Down_Response_{etf}'] = 0
                        else:
                            # Yeterli veri yoksa NaN değerler
                            symbol_data[f'Corr_{etf}'] = np.nan
                            symbol_data[f'Lag_Effect_{etf}'] = np.nan
                            symbol_data[f'Direction_Match_{etf}'] = np.nan
                            symbol_data[f'Up_Response_{etf}'] = np.nan
                            symbol_data[f'Down_Response_{etf}'] = np.nan
            
            correlation_data.append(symbol_data)
        
        self.correlation_data = pd.DataFrame(correlation_data)
        print(f"{len(correlation_data)} hisse için gelişmiş ETF ilişki analizi hesaplandı")
        
        return self.correlation_data
    
    def extract_features(self):
        """
        Hisselerin özelliklerini çıkar
        - ETF korelasyonları
        - Volatilite
        - Tarihsel fiyat aralıkları ve davranışları
        - Hacim dinamikleri
        """
        print("Hisse özellikleri çıkarılıyor...")
        
        # Korelasyon verilerini kullan
        features = self.correlation_data.copy()
        
        # NaN değerleri doldur
        etf_columns = [f'Corr_{etf}' for etf in ETFS if f'Corr_{etf}' in features.columns]
        features[etf_columns] = features[etf_columns].fillna(0)
        
        # Beta hesapla (SPY'a göre)
        if 'Corr_SPY' in features.columns:
            for symbol, df in self.historical_data.items():
                if symbol in features['Symbol'].values:
                    symbol_returns = df['return'].dropna()
                    if 'SPY' in self.etf_data and len(symbol_returns) > 30:
                        spy_returns = self.etf_data['SPY']['return'].dropna()
                        common_dates = symbol_returns.index.intersection(spy_returns.index)
                        
                        if len(common_dates) > 30:
                            # Beta = Cov(r_i, r_m) / Var(r_m)
                            symbol_ret = symbol_returns.loc[common_dates]
                            spy_ret = spy_returns.loc[common_dates]
                            
                            beta = np.cov(symbol_ret, spy_ret)[0, 1] / np.var(spy_ret)
                            features.loc[features['Symbol'] == symbol, 'Beta'] = beta
        
        # Tarihsel fiyat ve hacim özellikleri
        for symbol, df in self.historical_data.items():
            if symbol in features['Symbol'].values and not df.empty:
                # Son fiyat
                features.loc[features['Symbol'] == symbol, 'Last_Price'] = df['close'].iloc[-1]
                
                # Tüm tarihsel veri üzerinden fiyat aralığı hesapla
                price_max = df['close'].max()
                price_min = df['close'].min()
                price_avg = df['close'].mean()
                
                # Fiyat aralığı ve değişkenlik metrikleri
                price_range_pct = (price_max - price_min) / price_min * 100
                features.loc[features['Symbol'] == symbol, 'Price_Range_Pct'] = price_range_pct
                
                # Şu anki fiyatın tarihsel aralıktaki konumu (0-100 arası, 0=min, 100=max)
                current_price = df['close'].iloc[-1]
                if price_max > price_min:  # Bölme hatası olmaması için kontrol
                    price_position = (current_price - price_min) / (price_max - price_min) * 100
                else:
                    price_position = 50  # Fiyat değişkenliği yoksa orta nokta
                features.loc[features['Symbol'] == symbol, 'Price_Position'] = price_position
                
                # Fiyatın medyan ve ortalamaya göre konumu
                price_median = df['close'].median()
                features.loc[features['Symbol'] == symbol, 'Price_Vs_Median_Pct'] = (current_price / price_median - 1) * 100
                features.loc[features['Symbol'] == symbol, 'Price_Vs_Avg_Pct'] = (current_price / price_avg - 1) * 100
                
                # Mutlak fiyat kategorisi (fiyat bandını sınıflandır)
                if current_price < 5:
                    price_category = 0  # Düşük fiyatlı (<$5)
                elif current_price < 25:
                    price_category = 1  # Orta-düşük ($5-$25)
                elif current_price < 100:
                    price_category = 2  # Orta-yüksek ($25-$100)
                else:
                    price_category = 3  # Yüksek fiyatlı (>$100)
                features.loc[features['Symbol'] == symbol, 'Price_Category'] = price_category
                
                # Hacim özellikleri
                if 'volume' in df.columns and df['volume'].mean() > 0:
                    features.loc[features['Symbol'] == symbol, 'Avg_Volume'] = df['volume'].mean()
                    features.loc[features['Symbol'] == symbol, 'Volume_Volatility'] = df['volume'].pct_change().std()
                    
                    # Hacim trendleri - tüm veri üzerinden 
                    volume_trend = np.polyfit(np.arange(len(df['volume'])), df['volume'].values, 1)[0]
                    norm_volume_trend = volume_trend / df['volume'].mean() * 100  # Normalize edilmiş trend
                    features.loc[features['Symbol'] == symbol, 'Volume_Trend'] = norm_volume_trend
        
        # Eksik değerleri doldur
        features = features.fillna(0)
        
        print("Hisse özellikleri çıkarıldı")
        return features

    def calculate_similarity(self):
        """
        Hisseler arasındaki benzerlikleri hesapla
        Historical ve EXTLT dosyalarından gelen hisseler için ayrı ayrı benzerlik matrisleri oluştur
        """
        print("Hisseler arasındaki benzerlikler hesaplanıyor...")
        
        # Özellikleri çıkar
        features = self.extract_features()
        
        # Historical ve EXTLT hisselerini ayır
        hist_features = features[features['Source'] == 'historical_data.csv']
        extlt_features = features[features['Source'] == 'extlthistorical.csv']
        
        # Benzerlik hesaplamasında kullanılacak sütunları seç
        similarity_columns = [col for col in features.columns if 
                             col.startswith('Corr_') or 
                             col in ['Volatility', 'Avg_Volume', 'Beta', 'Volume_Volatility']]
        
        # Benzerlik matrisleri
        if not hist_features.empty and len(similarity_columns) > 0:
            # Historical hisseleri için benzerlik matrisi
            hist_data = hist_features[similarity_columns].values
            hist_symbols = hist_features['Symbol'].values
            
            # Veriyi ölçeklendir
            scaler = StandardScaler()
            hist_data_scaled = scaler.fit_transform(hist_data)
            
            # Kosinüs benzerliği hesapla
            hist_similarity = cosine_similarity(hist_data_scaled)
            
            # DataFrame'e dönüştür
            self.similarity_matrix_hist = pd.DataFrame(hist_similarity, 
                                                    index=hist_symbols, 
                                                    columns=hist_symbols)
            
            print(f"Historical hisseler için {len(hist_symbols)}x{len(hist_symbols)} benzerlik matrisi oluşturuldu")
        
        if not extlt_features.empty and len(similarity_columns) > 0:
            # EXTLT hisseleri için benzerlik matrisi
            extlt_data = extlt_features[similarity_columns].values
            extlt_symbols = extlt_features['Symbol'].values
            
            # Veriyi ölçeklendir
            scaler = StandardScaler()
            extlt_data_scaled = scaler.fit_transform(extlt_data)
            
            # Kosinüs benzerliği hesapla
            extlt_similarity = cosine_similarity(extlt_data_scaled)
            
            # DataFrame'e dönüştür
            self.similarity_matrix_extlt = pd.DataFrame(extlt_similarity, 
                                                     index=extlt_symbols, 
                                                     columns=extlt_symbols)
            
            print(f"EXTLT hisseler için {len(extlt_symbols)}x{len(extlt_symbols)} benzerlik matrisi oluşturuldu")
        
        print("Benzerlik hesaplaması tamamlandı")
        
        return self.similarity_matrix_hist, self.similarity_matrix_extlt
    
    def create_sequence_dataset(self, symbol, window_size=20):
        """
        Hisse verilerini sequence (sıralı) veri setine dönüştür
        LSTM modelleri için girdi formatını hazırlar
        """
        if symbol not in self.historical_data or self.historical_data[symbol].empty:
            return None, None
        
        df = self.historical_data[symbol].copy()
        
        # Fiyat, hacim ve ETF ilişkileri içeren bir veri seti hazırla
        data_points = []
        
        # Fiyat değişimleri - log return oluştur (volatiliteye uygun)
        if 'close' in df.columns:
            df['log_return'] = np.log(df['close'] / df['close'].shift(1))
            # NaN değerleri temizle
            df = df.dropna()
            
            # Sequence verisi oluştur
            sequences = []
            for i in range(len(df) - window_size):
                # Her gözlem penceresi için
                seq = df['log_return'].values[i:i + window_size]
                sequences.append(seq)
            
            if sequences:
                return np.array(sequences), df.index[window_size:]
        
        return None, None
    
    def build_autoencoder_model(self, input_dim, encoding_dim=10):
        """
        Sıralı verileri kodlayan bir LSTM autoencoder modeli oluştur
        """
        if not HAVE_TENSORFLOW:
            print("TensorFlow kurulu değil, LSTM tabanlı analiz atlanıyor")
            return None
        
        # Encoder kısmı
        input_layer = Input(shape=(input_dim, 1))
        encoder = LSTM(64, activation='relu', return_sequences=False)(input_layer)
        encoder = Dropout(0.2)(encoder)
        encoder_output = Dense(encoding_dim, activation='relu')(encoder)
        
        # Decoder kısmı
        decoder = RepeatVector(input_dim)(encoder_output)
        decoder = LSTM(64, activation='relu', return_sequences=True)(decoder)
        decoder = Dropout(0.2)(decoder)
        decoder_output = TimeDistributed(Dense(1))(decoder)
        
        # Autoencoder modeli
        autoencoder = Model(inputs=input_layer, outputs=decoder_output)
        encoder_model = Model(inputs=input_layer, outputs=encoder_output)
        
        # Modeli derle
        autoencoder.compile(optimizer='adam', loss='mse')
        
        return autoencoder, encoder_model
    
    def learn_stock_behaviors(self, window_size=20, encoding_dim=10, epochs=50, batch_size=32):
        """
        Her hisse için davranış özelliklerini deep learning ile öğren
        """
        if not HAVE_TENSORFLOW:
            print("TensorFlow kurulu değil, basit özellik çıkarımı kullanılacak")
            return False
        
        print("Deep learning ile hisse davranışları öğreniliyor...")
        
        # Her bir veri kaynağı için özellik öğrenme işlemi
        for source, symbols in [('historical_data.csv', self.hist_symbols),
                               ('extlthistorical.csv', self.extlt_symbols)]:
            print(f"{source} kaynaklı hisseler işleniyor...")
            
            # Ortak modeli eğitmek için veri biriktir
            all_sequences = []
            symbol_indices = {}
            start_idx = 0
            
            # Tüm hisselerin sıralı verilerini topla
            for symbol in tqdm(symbols, desc=f"{source} veri hazırlama"):
                sequences, _ = self.create_sequence_dataset(symbol, window_size)
                
                if sequences is not None and len(sequences) > 0:
                    # Bu hissenin başlangıç ve bitiş indeksleri
                    end_idx = start_idx + len(sequences)
                    symbol_indices[symbol] = (start_idx, end_idx)
                    start_idx = end_idx
                    
                    # Tüm sequenceleri biriktir
                    all_sequences.extend(sequences)
            
            if not all_sequences:
                print(f"{source} için yeterli sıralı veri bulunamadı")
                continue
            
            # Numpy array'e dönüştür ve normalize et
            X = np.array(all_sequences).reshape(-1, window_size, 1)
            
            # Autoencoder modeli oluştur
            autoencoder, encoder = self.build_autoencoder_model(window_size, encoding_dim)
            
            # Early stopping için callback
            early_stopping = EarlyStopping(monitor='loss', patience=5, restore_best_weights=True)
            
            # Modeli eğit
            print(f"{source} için model eğitiliyor...")
            autoencoder.fit(X, X, 
                           epochs=epochs, 
                           batch_size=batch_size, 
                           shuffle=True,
                           callbacks=[early_stopping],
                           verbose=1)
            
            # Her hisse için kodlanmış temsilleri çıkar
            print(f"{source} için hisse kodlamaları çıkarılıyor...")
            for symbol, (start, end) in symbol_indices.items():
                # Bu hissenin sıralı verileri
                symbol_sequences = X[start:end]
                
                if len(symbol_sequences) > 0:
                    # Hissenin davranış kodlamasını çıkar
                    encoded_repr = encoder.predict(symbol_sequences)
                    # Ortalama kodlama - hissenin "parmak izi"
                    self.lstm_encodings[symbol] = np.mean(encoded_repr, axis=0)
                    
            print(f"{source} için {len(symbol_indices)} hissenin davranış kodlaması oluşturuldu")
        
        print("Hisse davranışları deep learning ile analiz edildi")
        return True
    
    def find_optimal_feature_weights(self):
        """
        Otomatik özellik ağırlıklandırma optimizasyonu 
        """
        print("Optimal özellik ağırlıkları hesaplanıyor...")
        
        # Tüm özellik grupları
        feature_groups = {
            'etf_correlations': 0.4,  # Başlangıç değeri
            'price_features': 0.2,    # Başlangıç değeri
            'volume_features': 0.15,  # Başlangıç değeri
            'volatility_features': 0.25  # Başlangıç değeri
        }
        
        # Özellikleri çıkar
        features = self.extract_features()
        
        # Otomatik ağırlık optimizasyonu için çeşitli ağırlık kombinasyonlarını dene
        # ve en uygun kümeleme sonucunu veren ağırlıkları bul
        best_silhouette = -1
        best_weights = feature_groups.copy()
        
        # Siliyet skoru hesaplamak için
        from sklearn.metrics import silhouette_score
        
        # Grid search ile ağırlıkları optimize et
        weight_combos = [
            {'etf_correlations': 0.40, 'price_features': 0.20, 'volume_features': 0.15, 'volatility_features': 0.25},
            {'etf_correlations': 0.35, 'price_features': 0.25, 'volume_features': 0.15, 'volatility_features': 0.25},
            {'etf_correlations': 0.30, 'price_features': 0.30, 'volume_features': 0.15, 'volatility_features': 0.25},
            {'etf_correlations': 0.45, 'price_features': 0.15, 'volume_features': 0.15, 'volatility_features': 0.25},
            {'etf_correlations': 0.35, 'price_features': 0.20, 'volume_features': 0.20, 'volatility_features': 0.25},
            {'etf_correlations': 0.30, 'price_features': 0.20, 'volume_features': 0.20, 'volatility_features': 0.30},
        ]
        
        for weights in weight_combos:
            # Özellik gruplarını ayır
            etf_columns = [col for col in features.columns if 
                          col.startswith('Corr_') or 
                          col.startswith('Lag_Effect_') or 
                          col.startswith('Direction_Match_') or
                          col.startswith('Up_Response_') or
                          col.startswith('Down_Response_')]
            
            price_columns = ['Last_Price', 'Price_Range_Pct', 'Price_Position', 
                           'Price_Vs_Median_Pct', 'Price_Vs_Avg_Pct', 'Price_Category']
            
            volume_columns = ['Avg_Volume', 'Volume_Volatility', 'Volume_Trend']
            
            volatility_columns = ['Volatility', 'Beta']
            
            # Her iki veri kaynağı için test et
            for source, symbol_list in [('historical_data.csv', self.hist_symbols), 
                                       ('extlthistorical.csv', self.extlt_symbols)]:
                if not symbol_list:
                    continue
                
                # Sadece bu kaynaktan gelen hisseleri filtrele
                src_features = features[features['Source'] == source]
                
                if src_features.empty:
                    continue
                
                # Sütunları kontrol et ve sadece var olanları kullan
                valid_columns = []
                weight_sum = 0.0
                
                # ETF sütunları
                valid_etf_cols = [col for col in etf_columns if col in src_features.columns]
                if valid_etf_cols:
                    valid_columns.extend(valid_etf_cols)
                    weight_sum += weights['etf_correlations']
                
                # Fiyat sütunları
                valid_price_cols = [col for col in price_columns if col in src_features.columns]
                if valid_price_cols:
                    valid_columns.extend(valid_price_cols)
                    weight_sum += weights['price_features']
                
                # Hacim sütunları
                valid_volume_cols = [col for col in volume_columns if col in src_features.columns]
                if valid_volume_cols:
                    valid_columns.extend(valid_volume_cols)
                    weight_sum += weights['volume_features']
                
                # Volatilite sütunları
                valid_volatility_cols = [col for col in volatility_columns if col in src_features.columns]
                if valid_volatility_cols:
                    valid_columns.extend(valid_volatility_cols)
                    weight_sum += weights['volatility_features']
                
                # Toplam ağırlık normalize et (1.0 olacak şekilde)
                normalized_weights = {}
                for key, value in weights.items():
                    normalized_weights[key] = value / weight_sum if weight_sum > 0 else value
                
                # Özellik setini hazırla
                X = src_features[valid_columns].values
                
                # Null kontrol
                if np.isnan(X).any():
                    X = np.nan_to_num(X, nan=0.0)
                
                # Ölçeklendir
                X_scaled = StandardScaler().fit_transform(X)
                
                # Ağırlıklandırma uygula
                X_weighted = X_scaled.copy()
                
                # Her özellik grubu için ağırlık uygula
                col_index = 0
                
                # ETF sütunları
                for i in range(len(valid_etf_cols)):
                    X_weighted[:, col_index] *= normalized_weights['etf_correlations']
                    col_index += 1
                
                # Fiyat sütunları
                for i in range(len(valid_price_cols)):
                    X_weighted[:, col_index] *= normalized_weights['price_features']
                    col_index += 1
                
                # Hacim sütunları
                for i in range(len(valid_volume_cols)):
                    X_weighted[:, col_index] *= normalized_weights['volume_features']
                    col_index += 1
                
                # Volatilite sütunları
                for i in range(len(valid_volatility_cols)):
                    X_weighted[:, col_index] *= normalized_weights['volatility_features']
                    col_index += 1
                
                # K-Means ile kümeleme
                n_clusters = min(self.n_groups, len(src_features))
                kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
                clusters = kmeans.fit_predict(X_weighted)
                
                # Kümeleme kalitesini değerlendir
                if len(np.unique(clusters)) > 1 and len(clusters) > n_clusters:
                    score = silhouette_score(X_weighted, clusters)
                    
                    # En iyi skoru tut
                    if score > best_silhouette:
                        best_silhouette = score
                        best_weights = weights.copy()
                        print(f"Daha iyi ağırlıklar bulundu! Siliyet skoru: {score:.4f}, Ağırlıklar: {weights}")
        
        self.optimal_weights = best_weights
        print(f"Optimal ağırlıklar: {best_weights}, Siliyet skoru: {best_silhouette:.4f}")
        return best_weights
    
    def cluster_stocks_with_deep_learning(self):
        """
        Deep learning ile öğrenilen davranış kodlamalarını kullanarak hisseleri grupla
        """
        print(f"Deep learning ile {self.n_groups} grup oluşturuluyor...")
        
        # LSTM ile davranış öğrenme
        dl_success = self.learn_stock_behaviors()
        
        # Optimal ağırlıkları bul
        if not self.optimal_weights:
            self.optimal_weights = self.find_optimal_feature_weights()
        
        # Özellikleri birleştir (LSTM kodlamaları + diğer özellikler)
        features = self.extract_features()
        
        # Historical ve EXTLT veri grupları için ayrı ayrı işlem yap
        for source, symbols in [('historical_data.csv', self.hist_symbols), 
                               ('extlthistorical.csv', self.extlt_symbols)]:
            if not symbols:
                print(f"{source} için sembol bulunamadı")
                continue
            
            # Bu kaynaktan gelen hisseleri filtrele
            source_features = features[features['Source'] == source]
            if source_features.empty:
                print(f"{source} için özellik bulunamadı")
                continue
            
            print(f"{source} için gruplandırma yapılıyor...")
            
            # LSTM kodlamalarını bu kaynak için ayrı bir veri çerçevesine topla
            lstm_df = pd.DataFrame(index=source_features['Symbol'])
            
            if dl_success and self.lstm_encodings:
                # Her hisse için LSTM kodlamasını ekle
                for symbol in source_features['Symbol']:
                    if symbol in self.lstm_encodings:
                        # Kodlamanın her boyutu için ayrı sütun
                        for i, val in enumerate(self.lstm_encodings[symbol]):
                            lstm_df.loc[symbol, f'LSTM_{i}'] = val
                
                # Eksik değerleri doldur
                lstm_df = lstm_df.fillna(0)
            
            # Standart özellikleri hazırla
            std_features = source_features.set_index('Symbol')
            feature_columns = [col for col in std_features.columns 
                           if col != 'Source' and col != 'Symbol']
            std_features = std_features[feature_columns]
            
            # LSTM kodlamaları varsa, standart özelliklerle birleştir
            if not lstm_df.empty and dl_success:
                # İki veri setini birleştir
                combined_features = pd.concat([std_features, lstm_df], axis=1)
                combined_features = combined_features.fillna(0)
                
                # Özellik gruplarını ayır
                etf_columns = [col for col in combined_features.columns if 
                           col.startswith('Corr_') or 
                           col.startswith('Lag_Effect_') or 
                           col.startswith('Direction_Match_') or
                           col.startswith('Up_Response_') or
                           col.startswith('Down_Response_')]
                
                price_columns = [col for col in combined_features.columns if 
                             col in ['Last_Price', 'Price_Range_Pct', 'Price_Position', 
                                   'Price_Vs_Median_Pct', 'Price_Vs_Avg_Pct', 'Price_Category']]
                
                volume_columns = [col for col in combined_features.columns if 
                              col in ['Avg_Volume', 'Volume_Volatility', 'Volume_Trend']]
                
                volatility_columns = [col for col in combined_features.columns if 
                                 col in ['Volatility', 'Beta']]
                
                lstm_columns = [col for col in combined_features.columns if col.startswith('LSTM_')]
                
                # Değerleri numpy array'e dönüştür
                X = combined_features.values
                
                # Null kontrol
                if np.isnan(X).any():
                    X = np.nan_to_num(X, nan=0.0)
                
                # Ölçeklendir
                X_scaled = StandardScaler().fit_transform(X)
                
                # Ağırlıklandırma uygula
                X_weighted = X_scaled.copy()
                
                # Her özellik grubu için indeks aralıklarını belirle
                col_indices = {}
                col_indices['etf'] = [i for i, col in enumerate(combined_features.columns) if col in etf_columns]
                col_indices['price'] = [i for i, col in enumerate(combined_features.columns) if col in price_columns]
                col_indices['volume'] = [i for i, col in enumerate(combined_features.columns) if col in volume_columns]
                col_indices['volatility'] = [i for i, col in enumerate(combined_features.columns) if col in volatility_columns]
                col_indices['lstm'] = [i for i, col in enumerate(combined_features.columns) if col in lstm_columns]
                
                # Ağırlıkları uygula
                for feature_type, indices in col_indices.items():
                    if indices:
                        if feature_type == 'etf':
                            weight = self.optimal_weights['etf_correlations']
                        elif feature_type == 'price':
                            weight = self.optimal_weights['price_features']
                        elif feature_type == 'volume':
                            weight = self.optimal_weights['volume_features']
                        elif feature_type == 'volatility':
                            weight = self.optimal_weights['volatility_features']
                        elif feature_type == 'lstm':
                            # LSTM kodlamaları için daha yüksek ağırlık (çünkü zaman serisi davranışını içerir)
                            weight = 0.5  # LSTM kodlamalarına %50 ağırlık ver
                        
                        for idx in indices:
                            X_weighted[:, idx] *= weight
                
                # Boyut indirgeme (PCA) - görselleştirme için
                pca = PCA(n_components=min(X_weighted.shape[1], 5))
                X_pca = pca.fit_transform(X_weighted)
                
                # K-Means ile kümeleme
                n_clusters = min(self.n_groups, len(combined_features))
                kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
                clusters = kmeans.fit_predict(X_weighted)  # Ağırlıklandırılmış verileri kullan
                
                # Sonuçları sakla
                if source == 'historical_data.csv':
                    self.groups_hist = dict(zip(combined_features.index, clusters))
                else:
                    self.groups_extlt = dict(zip(combined_features.index, clusters))
                
                # Benzer/hedge grupları göster
                hedge_candidates = {}
                
                # Her grup için
                for group_id in range(n_clusters):
                    # Bu gruptaki hisseler
                    group_symbols = [symbol for symbol, g in zip(combined_features.index, clusters) if g == group_id]
                    
                    if not group_symbols:
                        continue
                    
                    # Bu gruptaki hisselerin özelliklerini incele
                    group_features = combined_features.loc[group_symbols]
                    
                    # ETF tepkileri - özellikle SPY ve TLT tepkileri
                    spy_response = group_features['Corr_SPY'].mean() if 'Corr_SPY' in group_features.columns else 0
                    tlt_response = group_features['Corr_TLT'].mean() if 'Corr_TLT' in group_features.columns else 0
                    
                    print(f"Grup {group_id}: {len(group_symbols)} hisse, SPY korelasyonu: {spy_response:.4f}, TLT korelasyonu: {tlt_response:.4f}")
                    print(f"Örnek hisseler: {', '.join(group_symbols[:5])}...")
                    
                    # Hedge aday grupları belirle (ters korelasyonlar)
                    for other_id in range(n_clusters):
                        if other_id != group_id:
                            # Diğer gruptaki hisseler
                            other_symbols = [symbol for symbol, g in zip(combined_features.index, clusters) if g == other_id]
                            
                            if not other_symbols:
                                continue
                            
                            # Diğer gruptaki hisselerin ETF tepkileri
                            other_features = combined_features.loc[other_symbols]
                            other_spy = other_features['Corr_SPY'].mean() if 'Corr_SPY' in other_features.columns else 0
                            other_tlt = other_features['Corr_TLT'].mean() if 'Corr_TLT' in other_features.columns else 0
                            
                            # Korelasyon zıtlığını hesapla
                            spy_diff = spy_response * other_spy
                            tlt_diff = tlt_response * other_tlt
                            
                            # Negatif korelasyonlar hedge için idealdir
                            hedge_score = -1 * (spy_diff + tlt_diff)
                            
                            # Yüksek hedge skoru olan grupları sakla
                            if hedge_score > 0.1:  # Belirli bir eşiğin üstünde olanlar
                                if group_id not in hedge_candidates:
                                    hedge_candidates[group_id] = []
                                
                                hedge_candidates[group_id].append((other_id, hedge_score))
                
                # Hedge sonuçlarını göster
                print("\nHEDGE GRUBU ÖNERİLERİ:")
                for group_id, candidates in hedge_candidates.items():
                    if candidates:
                        # Hedge skorlarına göre sırala
                        sorted_candidates = sorted(candidates, key=lambda x: x[1], reverse=True)
                        best_match = sorted_candidates[0]
                        print(f"Grup {group_id} hisseleri için ideal hedge: Grup {best_match[0]} (Skor: {best_match[1]:.4f})")
                        
                        # Örnek hisseler
                        group_examples = [symbol for symbol, g in zip(combined_features.index, clusters) if g == group_id][:3]
                        hedge_examples = [symbol for symbol, g in zip(combined_features.index, clusters) if g == best_match[0]][:3]
                        
                        print(f"  Örnek: {', '.join(group_examples)} LONG + {', '.join(hedge_examples)} SHORT")
                
                print(f"{source} için deep learning destekli gruplandırma tamamlandı.")
            else:
                # LSTM kodlamaları yoksa sadece standart özellikleri kullan
                print(f"{source} için sadece standart özellikler kullanılıyor...")
                
                X = std_features.values
                
                # Null kontrol
                if np.isnan(X).any():
                    X = np.nan_to_num(X, nan=0.0)
                
                # Ölçeklendir ve kümeleme yap
                X_scaled = StandardScaler().fit_transform(X)
                
                # K-Means ile kümeleme
                n_clusters = min(self.n_groups, len(std_features))
                kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
                clusters = kmeans.fit_predict(X_scaled)
                
                # Sonuçları sakla
                if source == 'historical_data.csv':
                    self.groups_hist = dict(zip(std_features.index, clusters))
                else:
                    self.groups_extlt = dict(zip(std_features.index, clusters))
        
        return self.groups_hist, self.groups_extlt

    def save_results(self):
        """Kümeleme sonuçlarını CSV dosyalarına kaydet"""
        print("Sonuçlar kaydediliyor...")
        
        # Historical hisseler için sonuçlar
        if self.groups_hist:
            hist_results = []
            for symbol, group in self.groups_hist.items():
                hist_results.append({
                    'Symbol': symbol,
                    'Group': group,
                    'Source': 'historical_data.csv'
                })
            
            hist_df = pd.DataFrame(hist_results)
            hist_df.to_csv("mastermind_historical_results.csv", index=False)
            print(f"Historical sonuçlar 'mastermind_historical_results.csv' dosyasına kaydedildi.")
        
        # EXTLT hisseler için sonuçlar
        if self.groups_extlt:
            extlt_results = []
            for symbol, group in self.groups_extlt.items():
                extlt_results.append({
                    'Symbol': symbol,
                    'Group': group,
                    'Source': 'extlthistorical.csv'
                })
            
            extlt_df = pd.DataFrame(extlt_results)
            extlt_df.to_csv("mastermind_extlt_results.csv", index=False)
            print(f"EXTLT sonuçlar 'mastermind_extlt_results.csv' dosyasına kaydedildi.")
        
        # Tüm sonuçları birleştirip kaydet
        all_results = []
        
        for symbol, group in self.groups_hist.items():
            all_results.append({
                'Symbol': symbol,
                'Group': group,
                'Source': 'historical_data.csv'
            })
            
        for symbol, group in self.groups_extlt.items():
            all_results.append({
                'Symbol': symbol,
                'Group': group,
                'Source': 'extlthistorical.csv'
            })
        
        if all_results:
            all_df = pd.DataFrame(all_results)
            all_df.to_csv("mastermind_all_results.csv", index=False)
            print(f"Tüm sonuçlar 'mastermind_all_results.csv' dosyasına kaydedildi.")
        
        print("Sonuçlar başarıyla kaydedildi.")
    
    def visualize_groups(self):
        """Grupları görselleştir"""
        print("Gruplar görselleştiriliyor...")
        
        # Historical ve EXTLT için görselleştirme yap
        for data_source, groups in [("Historical", self.groups_hist), 
                                    ("EXTLT", self.groups_extlt)]:
            if not groups:
                print(f"{data_source} için görselleştirme yapılamıyor (veri yok)")
                continue
            
            # Grup başına sembol sayısını hesapla
            group_counts = {}
            for group in set(groups.values()):
                group_counts[group] = sum(1 for g in groups.values() if g == group)
            
            # Grup büyüklüklerini görselleştir
            plt.figure(figsize=(10, 6))
            
            # Barlar
            bars = plt.bar(group_counts.keys(), group_counts.values())
            
            # Etiketler
            plt.title(f"{data_source} Veri Setinde Grup Büyüklükleri")
            plt.xlabel("Grup Numarası")
            plt.ylabel("Hisse Sayısı")
            plt.xticks(list(group_counts.keys()))
            
            # Her barın üstüne değer yaz
            for bar in bars:
                height = bar.get_height()
                plt.text(bar.get_x() + bar.get_width()/2., height,
                        f'{height}', ha='center', va='bottom')
            
            # Kaydet
            plt.savefig(f"mastermind_{data_source.lower()}_group_sizes.png")
            plt.close()
            
            print(f"{data_source} grup büyüklükleri görselleştirildi.")
            
        print("Görselleştirme tamamlandı.")
    
    def visualize_correlations(self):
        """Her grup için ETF korelasyonlarını görselleştir"""
        print("Grup ETF korelasyonları görselleştiriliyor...")
        
        if self.correlation_data is None:
            print("Korelasyon verisi hesaplanmamış.")
            return
        
        # ETF korelasyon sütunları
        etf_columns = [col for col in self.correlation_data.columns if col.startswith('Corr_')]
        
        # Her veri seti için görselleştirme yap
        for data_source, groups in [("Historical", self.groups_hist), 
                                    ("EXTLT", self.groups_extlt)]:
            if not groups:
                print(f"{data_source} için görselleştirme yapılamıyor (veri yok)")
                continue
            
            # Her grup için ortalama ETF korelasyonlarını hesapla
            group_corrs = {}
            for group in set(groups.values()):
                # Bu gruptaki hisseler
                group_symbols = [symbol for symbol, g in groups.items() if g == group]
                
                # Bu hisselerin ETF korelasyonları
                group_df = self.correlation_data[self.correlation_data['Symbol'].isin(group_symbols)]
                
                # Her ETF için ortalama korelasyon
                group_corrs[group] = {}
                for etf_col in etf_columns:
                    etf_name = etf_col.replace('Corr_', '')
                    group_corrs[group][etf_name] = group_df[etf_col].mean()
            
            # Görselleştirme
            plt.figure(figsize=(15, 8))
            
            # Her grup için bir çizgi çiz
            for group in group_corrs:
                plt.plot([col.replace('Corr_', '') for col in etf_columns], 
                        [group_corrs[group][etf.replace('Corr_', '')] for etf in etf_columns],
                        marker='o', label=f'Grup {group}')
            
            plt.axhline(y=0, color='black', linestyle='--', alpha=0.3)
            
            plt.title(f"{data_source} Grupları ETF Korelasyonları")
            plt.xlabel("ETF")
            plt.ylabel("Ortalama Korelasyon")
            plt.legend()
            plt.grid(True, alpha=0.3)
            
            # Kaydet
            plt.savefig(f"mastermind_{data_source.lower()}_etf_correlations.png")
            plt.close()
            
            print(f"{data_source} ETF korelasyonları görselleştirildi.")
            
        print("Korelasyon görselleştirmesi tamamlandı.")
    
    def run_analysis(self):
        """Tüm analiz adımlarını çalıştır"""
        try:
            # 1. Sembolleri yükle
            self.load_symbols_from_csv()
            
            # 2. Tarihsel verileri yükle veya çek
            data_loaded = self.load_historical_data()
            
            # Veri yoksa API'den çek
            if not data_loaded:
                print("Veriler yüklenemedi, API'den çekiliyor...")
                try:
                    # IBKR'ye bağlan
                    connected = self.connect_to_ibkr()
                    
                    if connected:
                        # Verileri çek
                        self.fetch_all_historical_data()
                        
                        # Verileri kaydet
                        self.save_historical_data()
                        
                        # IBKR bağlantısını kapat
                        self.disconnect_from_ibkr()
                    else:
                        print("IBKR bağlantısı kurulamadı, analiz durduruluyor.")
                        return
                except Exception as e:
                    print(f"Veri çekme hatası: {e}")
                    return
            
            # 3. Getirileri hesapla
            self.calculate_returns()
            
            # 4. ETF korelasyonlarını hesapla
            self.calculate_correlations_with_etfs()
            
            # 5. Otomatik özellik ağırlıklandırma
            self.find_optimal_feature_weights()
            
            # 6. Deep learning ile hisse davranışlarını analiz et ve gruplandır
            self.cluster_stocks_with_deep_learning()
            
            # 7. Sonuçları kaydet
            self.save_results()
            
            # 8. Görselleştirmeleri oluştur
            self.visualize_groups()
            self.visualize_correlations()
            
            print("Mastermind analizi başarıyla tamamlandı!")
            
        except Exception as e:
            print(f"Analiz sırasında hata oluştu: {e}")
            import traceback
            traceback.print_exc()

# Programı çalıştır
if __name__ == "__main__":
    analyzer = MastermindAnalysis()
    analyzer.run_analysis() 