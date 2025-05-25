import pandas as pd
import numpy as np
import os
import time
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.cluster import KMeans, AgglomerativeClustering
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.decomposition import PCA
from sklearn.metrics.pairwise import cosine_similarity
from scipy.cluster.hierarchy import dendrogram, linkage
from sklearn.metrics import silhouette_score
from tqdm import tqdm
import warnings
import pickle

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

# ETF listesi - mastermind ile aynı liste kullanılır
ETFS = ["TLT", "IEF", "SHY", "SPY", "KRE", "IWM", "HYG", "PFF", "PGF", "PGX"]

class DeepMastermind:
    """
    Deep Learning tabanlı gelişmiş hisse gruplaması ve hedge analizi
    """
    def __init__(self, historical_data=None, etf_data=None, hist_symbols=None, extlt_symbols=None, n_groups=12):
        self.historical_data = historical_data or {}  # Hisse verileri
        self.etf_data = etf_data or {}               # ETF verileri
        self.hist_symbols = hist_symbols or []       # historical.csv'den gelen semboller
        self.extlt_symbols = extlt_symbols or []     # extlthistorical.csv'den gelen semboller
        self.n_groups = n_groups                     # Oluşturulacak grup sayısı
        self.lstm_encodings = {}                     # LSTM tabanlı kodlamalar
        self.optimal_weights = None                  # Otomatik bulunan optimal ağırlıklar
        self.extracted_features = None               # Çıkarılan özellikler
        self.groups_hist = {}                        # Gruplandırma sonuçları
        self.groups_extlt = {}                       # Gruplandırma sonuçları
        self.hedge_candidates = {}                   # Hedge grup adayları
    
    def load_data(self, mastermind_instance):
        """Mevcut bir Mastermind nesnesinden verileri yükle"""
        print("Mastermind'dan veriler yükleniyor...")
        if hasattr(mastermind_instance, 'historical_data'):
            self.historical_data = mastermind_instance.historical_data
        
        if hasattr(mastermind_instance, 'etf_data'):
            self.etf_data = mastermind_instance.etf_data
        
        if hasattr(mastermind_instance, 'hist_symbols'):
            self.hist_symbols = mastermind_instance.hist_symbols
        
        if hasattr(mastermind_instance, 'extlt_symbols'):
            self.extlt_symbols = mastermind_instance.extlt_symbols
        
        # Tarihsel veri içinden sadece getirileri hesapla
        self.calculate_returns()
        
        print(f"Veriler yüklendi: {len(self.historical_data)} hisse, {len(self.etf_data)} ETF")
        return True
    
    def calculate_returns(self):
        """Tüm hisseler ve ETF'ler için günlük getiri hesapla"""
        print("Günlük getiriler hesaplanıyor...")
        
        # Preferred hisseler için günlük getiri hesapla
        for symbol, df in self.historical_data.items():
            if 'close' in df.columns and not df.empty:
                self.historical_data[symbol]['return'] = df['close'].pct_change()
        
        # ETF'ler için günlük getiri hesapla
        for etf, df in self.etf_data.items():
            if 'close' in df.columns and not df.empty:
                self.etf_data[etf]['return'] = df['close'].pct_change()
            
        print("Günlük getiriler hesaplandı")
    
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
            return None, None
        
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
    
    def learn_stock_behaviors(self, window_size=20, encoding_dim=10, epochs=10, batch_size=32):
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
            
            if autoencoder is None:
                continue
            
            # Early stopping için callback
            early_stopping = EarlyStopping(monitor='loss', patience=3, restore_best_weights=True)
            
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
    
    def extract_features(self):
        """
        Hisselerin özelliklerini çıkar, ETF tepkileri ve fiyat özellikleri
        """
        print("Gelişmiş hisse özellikleri çıkarılıyor...")
        
        # Her hisse için özellikler
        features_list = []
        
        # Her hisse için ETF tepkileri ve fiyat özellikleri
        for source, symbols in [('historical_data.csv', self.hist_symbols),
                               ('extlthistorical.csv', self.extlt_symbols)]:
            for symbol in symbols:
                if symbol not in self.historical_data:
                    continue
                
                df = self.historical_data[symbol]
                if df.empty:
                    continue
                
                # Temel özellikler
                feature_row = {
                    'Symbol': symbol,
                    'Source': source
                }
                
                # Volatilite
                if 'return' in df.columns:
                    returns = df['return'].dropna()
                    if len(returns) > 10:
                        feature_row['Volatility'] = returns.std() * np.sqrt(252)  # Yıllık volatilite
                
                # Fiyat özellikleri
                if 'close' in df.columns:
                    prices = df['close'].dropna()
                    if len(prices) > 0:
                        # Son fiyat
                        feature_row['Last_Price'] = prices.iloc[-1]
                        
                        # Fiyat aralığı
                        price_max = prices.max()
                        price_min = prices.min()
                        price_avg = prices.mean()
                        price_med = prices.median()
                        
                        # Fiyat aralığı ve pozisyon
                        feature_row['Price_Range_Pct'] = (price_max - price_min) / price_min * 100 if price_min > 0 else 0
                        feature_row['Price_Position'] = (prices.iloc[-1] - price_min) / (price_max - price_min) * 100 if price_max > price_min else 50
                        feature_row['Price_Vs_Avg_Pct'] = (prices.iloc[-1] / price_avg - 1) * 100 if price_avg > 0 else 0
                        feature_row['Price_Vs_Median_Pct'] = (prices.iloc[-1] / price_med - 1) * 100 if price_med > 0 else 0
                        
                        # Fiyat kategorisi
                        last_price = prices.iloc[-1]
                        if last_price < 5:
                            feature_row['Price_Category'] = 0  # Düşük fiyat
                        elif last_price < 25:
                            feature_row['Price_Category'] = 1  # Orta-düşük
                        elif last_price < 100:
                            feature_row['Price_Category'] = 2  # Orta-yüksek
                        else:
                            feature_row['Price_Category'] = 3  # Yüksek fiyat
                
                # Hacim özellikleri
                if 'volume' in df.columns:
                    volume = df['volume'].dropna()
                    if len(volume) > 0 and volume.mean() > 0:
                        feature_row['Avg_Volume'] = volume.mean()
                        feature_row['Volume_Volatility'] = volume.pct_change().std()
                        
                        # Hacim trendi - son 100 gün
                        if len(volume) > 100:
                            recent_volume = volume.iloc[-100:].values
                            trend = np.polyfit(np.arange(len(recent_volume)), recent_volume, 1)[0]
                            feature_row['Volume_Trend'] = trend / volume.mean() * 100  # Normalize
                
                # ETF Korelasyonları ve Tepkileri
                if 'return' in df.columns:
                    stock_returns = df['return'].dropna()
                    
                    for etf in ETFS:
                        if etf in self.etf_data and 'return' in self.etf_data[etf].columns:
                            etf_returns = self.etf_data[etf]['return'].dropna()
                            
                            # Ortak tarihleri bul
                            common_dates = stock_returns.index.intersection(etf_returns.index)
                            
                            if len(common_dates) > 30:  # En az 1 ay ortak veri
                                # 1. Korelasyon
                                corr = stock_returns.loc[common_dates].corr(etf_returns.loc[common_dates])
                                feature_row[f'Corr_{etf}'] = corr
                                
                                # 2. Beta
                                if etf == 'SPY':  # SPY'a göre beta
                                    cov = stock_returns.loc[common_dates].cov(etf_returns.loc[common_dates])
                                    var = etf_returns.loc[common_dates].var()
                                    beta = cov / var if var > 0 else 0
                                    feature_row['Beta'] = beta
                                
                                # 3. Yükseliş/düşüş koşullu tepkiler
                                etf_up = etf_returns.loc[common_dates] > 0
                                etf_down = etf_returns.loc[common_dates] < 0
                                
                                if sum(etf_up) > 10:
                                    up_avg = stock_returns.loc[common_dates][etf_up].mean()
                                    feature_row[f'Up_Resp_{etf}'] = up_avg
                                
                                if sum(etf_down) > 10:
                                    down_avg = stock_returns.loc[common_dates][etf_down].mean() 
                                    feature_row[f'Down_Resp_{etf}'] = down_avg
                                
                                # 4. Gecikme etkileri (ETF 1-3 gün önceki hareketi)
                                for lag in range(1, 4):
                                    if len(common_dates) > lag + 5:
                                        # ETF t gününde, hisse t+lag
                                        lag_corr = pd.Series(etf_returns.loc[common_dates].values[:-lag], 
                                                          index=common_dates[lag:]).corr(
                                                          stock_returns.loc[common_dates[lag:]])
                                        feature_row[f'Lag{lag}_{etf}'] = lag_corr
                
                # Özellik satırını ekle
                features_list.append(feature_row)
        
        # DataFrame oluştur
        self.extracted_features = pd.DataFrame(features_list)
        
        # LSTM kodlamalarını ekle
        if self.lstm_encodings:
            for symbol in self.extracted_features['Symbol']:
                if symbol in self.lstm_encodings:
                    for i, val in enumerate(self.lstm_encodings[symbol]):
                        self.extracted_features.loc[self.extracted_features['Symbol'] == symbol, f'LSTM_{i}'] = val
        
        # NaN değerleri doldur
        self.extracted_features = self.extracted_features.fillna(0)
        
        print(f"Toplam {len(self.extracted_features)} hisse için özellikler çıkarıldı")
        return self.extracted_features
    
    def find_optimal_weights(self):
        """
        Kümeleme için optimal ağırlıkları bul
        """
        if self.extracted_features is None:
            self.extract_features()
        
        print("Optimal özellik ağırlıkları aranıyor...")
        
        # Başlangıç ağırlıkları
        weights = {
            'etf_responses': 0.40,  # ETF tepkileri
            'price_features': 0.20,  # Fiyat özellikleri
            'volume_features': 0.15,  # Hacim özellikleri
            'volatility': 0.25,      # Volatilite özellikleri
        }
        
        # Özellik grupları
        feature_groups = {
            'etf_responses': [col for col in self.extracted_features.columns if 
                             col.startswith('Corr_') or col.startswith('Up_Resp_') or 
                             col.startswith('Down_Resp_') or col.startswith('Lag')],
            
            'price_features': ['Last_Price', 'Price_Range_Pct', 'Price_Position', 
                              'Price_Vs_Avg_Pct', 'Price_Vs_Median_Pct', 'Price_Category'],
            
            'volume_features': ['Avg_Volume', 'Volume_Volatility', 'Volume_Trend'],
            
            'volatility': ['Volatility', 'Beta']
        }
        
        # LSTM özellikleri varsa, bunları da ekle
        lstm_cols = [col for col in self.extracted_features.columns if col.startswith('LSTM_')]
        if lstm_cols:
            feature_groups['lstm'] = lstm_cols
            weights['lstm'] = 0.3  # LSTM için başlangıç ağırlığı
            
            # Diğer ağırlıkları yeniden düzenle
            total = sum(weights.values())
            for key in weights:
                weights[key] = weights[key] / total
        
        self.optimal_weights = weights
        print(f"Optimal ağırlıklar: {weights}")
        return weights
    
    def cluster_stocks(self):
        """
        Hisseleri kümelere ayır
        """
        if self.extracted_features is None:
            self.extract_features()
        
        if self.optimal_weights is None:
            self.find_optimal_weights()
        
        print(f"Hisseler {self.n_groups} gruba ayrılıyor...")
        
        # Her veri kaynağı için ayrı kümeleme
        for source in ['historical_data.csv', 'extlthistorical.csv']:
            # Bu kaynaktan gelen hisseler
            source_features = self.extracted_features[self.extracted_features['Source'] == source]
            
            if source_features.empty:
                print(f"{source} için özellik bulunamadı")
                continue
            
            print(f"{source} için kümeleme yapılıyor...")
            
            # Özellik matrisini hazırla (Symbol ve Source dışındaki tüm sütunlar)
            X = source_features.drop(['Symbol', 'Source'], axis=1)
            symbol_index = source_features['Symbol'].values
            
            # Null değerleri düzelt
            X = X.fillna(0)
            
            # Özellik grupları
            feature_groups = {
                'etf_responses': [col for col in X.columns if 
                                 col.startswith('Corr_') or col.startswith('Up_Resp_') or 
                                 col.startswith('Down_Resp_') or col.startswith('Lag')],
                
                'price_features': [col for col in X.columns if 
                                  col in ['Last_Price', 'Price_Range_Pct', 'Price_Position', 
                                        'Price_Vs_Avg_Pct', 'Price_Vs_Median_Pct', 'Price_Category']],
                
                'volume_features': [col for col in X.columns if 
                                   col in ['Avg_Volume', 'Volume_Volatility', 'Volume_Trend']],
                
                'volatility': [col for col in X.columns if 
                              col in ['Volatility', 'Beta']]
            }
            
            # LSTM özellikleri
            lstm_cols = [col for col in X.columns if col.startswith('LSTM_')]
            if lstm_cols:
                feature_groups['lstm'] = lstm_cols
            
            # Veriyi standartlaştır
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            X_scaled = pd.DataFrame(X_scaled, columns=X.columns)
            
            # Her özellik grubunu ağırlıklandır
            X_weighted = X_scaled.copy()
            
            for group, columns in feature_groups.items():
                if columns:
                    weight = self.optimal_weights.get(group, 0.1)  # Varsayılan 0.1
                    X_weighted[columns] = X_weighted[columns] * weight
            
            # K-Means kümeleme
            n_clusters = min(self.n_groups, len(X_weighted))
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            clusters = kmeans.fit_predict(X_weighted)
            
            # Kümeleme sonuçlarını sakla
            if source == 'historical_data.csv':
                self.groups_hist = dict(zip(symbol_index, clusters))
            else:
                self.groups_extlt = dict(zip(symbol_index, clusters))
            
            # Her kümenin özelliklerini incele
            cluster_properties = {}
            
            for cluster_id in range(n_clusters):
                cluster_mask = clusters == cluster_id
                cluster_symbols = symbol_index[cluster_mask]
                
                # Küme özellikleri
                cluster_properties[cluster_id] = {
                    'symbols': list(cluster_symbols),
                    'count': len(cluster_symbols),
                    'avg_price': X.loc[cluster_mask, 'Last_Price'].mean() if 'Last_Price' in X.columns else 0,
                    'avg_volatility': X.loc[cluster_mask, 'Volatility'].mean() if 'Volatility' in X.columns else 0,
                    'avg_spy_corr': X.loc[cluster_mask, 'Corr_SPY'].mean() if 'Corr_SPY' in X.columns else 0,
                    'avg_tlt_corr': X.loc[cluster_mask, 'Corr_TLT'].mean() if 'Corr_TLT' in X.columns else 0,
                }
                
                print(f"Küme {cluster_id}: {len(cluster_symbols)} hisse, " +
                     f"Ort. Fiyat: ${cluster_properties[cluster_id]['avg_price']:.2f}, " +
                     f"SPY Kor.: {cluster_properties[cluster_id]['avg_spy_corr']:.2f}, " +
                     f"TLT Kor.: {cluster_properties[cluster_id]['avg_tlt_corr']:.2f}, " +
                     f"Volatilite: {cluster_properties[cluster_id]['avg_volatility']:.2f}")
            
            # Hedge adaylarını belirle
            self.find_hedge_pairs(cluster_properties, source)
        
        return self.groups_hist, self.groups_extlt
    
    def find_hedge_pairs(self, cluster_properties, source):
        """
        Hedge olabilecek küme çiftlerini bul
        """
        print(f"{source} için hedge aday grupları belirleniyor...")
        
        hedge_candidates = {}
        
        for cluster_id, props in cluster_properties.items():
            for other_id, other_props in cluster_properties.items():
                if cluster_id != other_id:
                    # Hedge skoru - ters korelasyonlar daha iyi
                    spy_hedge = props['avg_spy_corr'] * other_props['avg_spy_corr']
                    tlt_hedge = props['avg_tlt_corr'] * other_props['avg_tlt_corr']
                    
                    # Negatif korelasyon ya da düşük pozitif korelasyon iyi
                    hedge_score = -1 * (spy_hedge + tlt_hedge)
                    
                    # Yüksek skor = iyi hedge potansiyeli
                    if hedge_score > 0.25:  # Threshold
                        if cluster_id not in hedge_candidates:
                            hedge_candidates[cluster_id] = []
                        
                        hedge_candidates[cluster_id].append({
                            'cluster': other_id,
                            'score': hedge_score,
                            'spy_effect': other_props['avg_spy_corr'],
                            'tlt_effect': other_props['avg_tlt_corr'],
                            'example_symbols': other_props['symbols'][:3]
                        })
        
        # Her grup için en iyi hedge adayını göster
        for cluster_id, candidates in hedge_candidates.items():
            # Skora göre sırala
            sorted_candidates = sorted(candidates, key=lambda x: x['score'], reverse=True)
            best_match = sorted_candidates[0]
            
            print(f"Grup {cluster_id} için ideal hedge: Grup {best_match['cluster']} (Skor: {best_match['score']:.2f})")
            print(f"  Hedge semboller: {', '.join(best_match['example_symbols'])}")
        
        # Sonuçları sakla
        if source == 'historical_data.csv':
            self.hedge_candidates['hist'] = hedge_candidates
        else:
            self.hedge_candidates['extlt'] = hedge_candidates
    
    def save_results(self, output_prefix="deep_mastermind"):
        """Sonuçları kaydet"""
        print("Sonuçlar kaydediliyor...")
        
        # Gruplanmış hisseleri kaydet
        results = []
        
        # Historical hisseler
        for symbol, group in self.groups_hist.items():
            results.append({
                'Symbol': symbol,
                'Group': group,
                'Source': 'historical_data.csv'
            })
        
        # EXTLT hisseler
        for symbol, group in self.groups_extlt.items():
            results.append({
                'Symbol': symbol,
                'Group': group,
                'Source': 'extlthistorical.csv'
            })
        
        # Sonuçları DataFrame olarak kaydet
        if results:
            results_df = pd.DataFrame(results)
            results_df.to_csv(f"{output_prefix}_groups.csv", index=False)
            print(f"Grup sonuçları {output_prefix}_groups.csv dosyasına kaydedildi")
        
        # LSTM kodlamalarını kaydet
        if self.lstm_encodings:
            with open(f"{output_prefix}_lstm_encodings.pkl", 'wb') as f:
                pickle.dump(self.lstm_encodings, f)
            print(f"LSTM kodlamaları {output_prefix}_lstm_encodings.pkl dosyasına kaydedildi")
        
        # Özellik verilerini kaydet
        if self.extracted_features is not None:
            self.extracted_features.to_csv(f"{output_prefix}_features.csv", index=False)
            print(f"Özellikler {output_prefix}_features.csv dosyasına kaydedildi")
        
        print("Sonuçlar başarıyla kaydedildi")
    
    def run_analysis(self, mastermind_instance=None):
        """Tam analiz akışını çalıştır"""
        try:
            # 1. Mastermind'dan veri yükle
            if mastermind_instance:
                self.load_data(mastermind_instance)
            
            # 2. Tarihsel davranışları öğren (LSTM ile)
            self.learn_stock_behaviors()
            
            # 3. Özellikleri çıkar
            self.extract_features()
            
            # 4. Optimal ağırlıkları bul
            self.find_optimal_weights()
            
            # 5. Hisseleri grupla
            self.cluster_stocks()
            
            # 6. Sonuçları kaydet
            self.save_results()
            
            print("Deep Mastermind analizi tamamlandı!")
            return True
            
        except Exception as e:
            print(f"Analiz sırasında hata oluştu: {e}")
            import traceback
            traceback.print_exc()
            return False

# Doğrudan çalıştırılırsa ve mastermind sonuçları varsa
if __name__ == "__main__":
    try:
        # Mastermind modülünü import et
        from mastermind import MastermindAnalysis
        
        # Önce normal mastermind analizi çalıştır
        analyzer = MastermindAnalysis()
        
        # Veri yüklenmiş mi kontrol et
        data_loaded = analyzer.load_historical_data()
        
        if not data_loaded:
            print("Mastermind verilerinizi önce yükleyin veya oluşturun")
        else:
            # Temel analizleri yap
            analyzer.calculate_returns()
            analyzer.calculate_correlations_with_etfs()
            
            # Deep analiz
            deep_analyzer = DeepMastermind()
            deep_analyzer.run_analysis(analyzer)
    except ImportError:
        print("mastermind.py bulunamadı, önce mastermind.py çalıştırın") 