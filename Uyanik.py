import ctypes
import time

# ES_CONTINUOUS: Sürekli çalış, ES_SYSTEM_REQUIRED: Sistemi uyanık tut, ES_DISPLAY_REQUIRED: Ekranı açık tut
ctypes.windll.kernel32.SetThreadExecutionState(0x80000002 | 0x80000001)  # ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED

print("Sistem uyanık ve ekran açık kalacak. Kod çalışıyor...")

# Örnek: Kodunuzun çalıştığını simüle etmek için bir döngü
try:
    while True:
        print("Kod hala çalışıyor...")
        time.sleep(10)  # 10 saniyede bir mesaj yazdır
except KeyboardInterrupt:
    print("Kod durduruldu.")
    # İşiniz bittiğinde normal duruma dön
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)  # Normal durum