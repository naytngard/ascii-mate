# ✨ ASCII Mate (Yüzen Masaüstü ASCII Arkadaşı)

Ders çalışırken, kod yazarken veya kitap okurken masaüstünüzde PDF'lerin, VS Code'un ve pencerelerin **tam üzerinde** hiçbir arkaplan veya çerçeve olmadan süzülen, tamamen saydam, sürüklenebilir, büyütülebilir **115+ saf klasik ASCII & canlı 3B Shader animasyonu**.

---

## 🚀 Kurulum ve Başlatma

### 1. Tek Tıkla Başlatma (Windows)
Klasördeki **`baslat.bat`** dosyasına çift tıklayın.
- Gerekli paketler (`PyQt6`, `rich`) eksikse otomatik olarak kurulur.
- Sade ve canlı renkli **ASCII Mate Terminal Hub** açılır.

### 2. Komut Satırından Doğrudan Kullanım
```bash
# İnteraktif Terminal Hub'ını açar:
python main.py

# Doğrudan tek bir karakteri masaüstünde başlatır (ör. uyuyan kedi veya 3B Satürn):
python main.py --widget sleeping_cat
python main.py --widget saturn_3d

# Tüm 115+ animasyonu doğrular (saf klasik ASCII + 3B shader testi):
python tests/validate_library.py
```

### 3. Python Kurmadan Çalıştırmak İçin `.exe` Oluşturma
Klasördeki **`build_exe.bat`** dosyasına çift tıklayın (varsayılan olarak hızlı açılan **`dist/ASCII_Mate/ASCII_Mate.exe`** paketini `--onedir` ile oluşturur; tek dosya için `build_exe.bat onefile`). PyInstaller kullanarak uygulamayı taşınabilir klasöre paketler.

---

## 📁 Proje Klasör Yapısı
```text
ascii_mate/
├── baslat.bat                  # Tek tıkla başlatıcı
├── build_exe.bat               # Taşınabilir uygulama derleyici (--onedir)
├── ASCII_Mate.spec             # PyInstaller yapılandırması
├── main.py                     # Ana giriş noktası
├── config.json                 # Kullanıcı ayarları
├── requirements.txt
├── README.md
├── src/
│   ├── core/                   # Modeller, 3B shader motoru, parçacıklar, kütüphane
│   ├── gui/                    # Saydam widget, sağ tık menüsü, ayarlar, sistem tepsisi
│   └── cli/                    # Terminal Hub ve canlı önizleme
├── assets/
│   ├── animations/             # Kategorilere ayrılmış saf ASCII .ascii.json dosyaları
│   └── themes.json
└── tests/
    └── validate_library.py
```

---

## 🎮 Masaüstü Widget Kontrolleri

* **Sol Tık + Sürükle:** Karakteri ekranın istediğiniz köşesine taşıyın (konumu otomatik kaydedilir).
* **Mouse Tekerleği (Scroll) / `+` `-`:** Karakter boyutunu pürüzsüz büyütüp küçültün (`8 pt` – `42 pt`).
* **Üzerine Gelme (Hover):** Fare ile üzerine geldiğinizde tutmayı kolaylaştıran zarif noktalı bir çerçeve belirir; fare gidince tekrar tamamen görünmez olur.
* **Sağ Tık Menüsü:**
  * 💧 **Saydamlık:** `%15` ile `%100` arası canlı ayar + İnce Ayar Slider Paneli.
  * ⏱️ **Çalışma Zamanlayıcısı (Pomodoro):** `15 / 25 / 45 / 60 dk` veya özel dakika; süre dolduğunda *"Mola Zamanı! ✨"* mesajı verip zarifçe kapanır.
  * ⚡ **Animasyon Hızı:** `0.25x` – `3x` + manuel FPS.
  * 🎨 **Renk Modları:** Saf Beyaz, Krem, Matrix Yeşili, Amber CRT, Cyberpunk Neon, Pastel Lavanta, Buz Mavisi, Sakura, Altın, Gökkuşağı ve Özel Hex Renk Seçici.
  * ✨ **Efektler & Parçacıklar:** Kar yağışı, yağmur, şimşekli fırtına, buhar, kalpler, kıvılcımlar, yıldız tozu, uyku `Zzz` baloncukları, göz kırpma, yatay aynalama (`Flip`), yumuşak neon parıltı (`Glow`) ve her zeminde okunabilirlik sağlayan gölge/kontur (`Shadow`).
  * 👻 **Ders / Hayalet Modu (Click-Through):** Açıldığında widget altındaki PDF veya tarayıcıya tıklamanıza izin verir. *(Çıkmak için sağ alttaki **Sistem Tepsisi** ikonuna sağ tıklayıp kapatabilirsiniz.)*
* **Sürükle-Bırak (Drag & Drop):** Bilgisayarınızdaki bir `.ascii.json` veya `.txt` dosyasını doğrudan açık olan widget'ın üzerine sürükleyip bırakarak anında kütüphaneye ekleyip çalıştırabilirsiniz!

---

## 🌐 Topluluk Animasyonu Oluşturma (`.ascii.json` ve `.txt` Rehberi)

Kendi ASCII animasyonunuzu paylaşmak veya eklemek için iki yöntem vardır:

### Yöntem 1: Düz Metin (`.txt`)
Her kareyi **`===FRAME===`** satırıyla ayırarak bir `.txt` dosyası kaydedin:

```text
  /\_/\
 ( o.o )
  > ^ <
===FRAME===
  /\_/\
 ( -.- )
  > ^ <
```

Bu `.txt` dosyasını açık olan widget'ın üstüne sürükleyin veya Terminal Hub'da **`I`** tuşuna basarak içe aktarın — otomatik olarak `.ascii.json` formatına dönüştürülür ve hizalanır!

### Yöntem 2: Standart `.ascii.json` Formatı
Dosyalarınızı `assets/animations/community/` klasörüne `<isim>.ascii.json` olarak atabilirsiniz:

```json
{
  "schema_version": "1.0",
  "id": "cozy_snow_cloud",
  "name": "Kar Yağdıran Bulut",
  "category": "Topluluk / Özel Eklenenler",
  "author": "Adınız",
  "tags": ["bulut", "kar", "kış"],
  "default_fps": 4,
  "recommended_color": "pastel_blue",
  "particles": {
    "enabled_by_default": true,
    "type": "snow",
    "toggle_label": "Buluttan Kar Dökülsün",
    "spawn_area": "bottom",
    "density": "medium",
    "chars": ["*", "❄", ".", "·"]
  },
  "frames": [
    "   .--.    \n .-(    ). \n(___.__)__)",
    "   .--.    \n .-(    )~ \n(___.__)__)"
  ]
}
```

Desteklenen `particles.type` değerleri: `"none"`, `"snow"`, `"rain"`, `"lightning"`, `"steam"`, `"hearts"`, `"sparks"`, `"stars"`.
