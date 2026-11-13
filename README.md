# ✨ ASCII Mate (Yüzen Masaüstü ASCII Arkadaşı)

Ders çalışırken, kod yazarken veya kitap okurken masaüstünüzde PDF'lerin, VS Code'un ve pencerelerin **tam üzerinde** hiçbir arkaplan veya çerçeve olmadan süzülen, tamamen saydam, sürüklenebilir, büyütülebilir **125+ saf klasik ASCII & canlı 3B Shader animasyonu**.

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

# Tüm 125+ animasyonu doğrular (saf klasik ASCII + 3B shader testi):
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
* **Shift + Sol Tık (3B Orbit) / Serbest Bakış:** Canlı 3B modellerin kamera açısını (`pitch` / `yaw`) fareyle istediğiniz yöne çevirin.
* **Köşe/Kenar Tutmaçları, Mouse Tekerleği (Scroll) / `+` `-`:** Karakter boyutunu pürüzsüz büyütüp küçültün (`6 pt` – `48 pt`). 3B modellerde **Otomatik** çözünürlük modunda widget büyüdükçe ASCII ızgara yoğunluğu (`width × height`) da otomatik artar!
* **Üzerine Gelme (Hover):** Fare ile üzerine geldiğinizde tutma ve köşe/kenar boyutlandırma tutmaçları belirir; fare gidince tekrar tamamen görünmez olur.
* **Sağ Tık Menüsü:**
  * 💧 **Saydamlık:** `%15` ile `%100` arası canlı ayar + İnce Ayar Slider Paneli.
  * 🖥️ **3B Izgara Çözünürlüğü:** Kompakt (`38×18`), Standart (`52×24`), HD (`64×30`), Ultra HD (`74×34`) veya Büyütmeye Göre Otomatik.
  * ⏱️ **Çalışma Zamanlayıcısı (Pomodoro):** `15 / 25 / 45 / 60 dk` veya özel dakika (`3B Kum Saati` kalan süreyle senkron akar!); süre dolduğunda **5 saniyelik canlı 3B Havai Fişek kutlaması** oynatır ve isteğe bağlı **5 dakikalık mola sayacına** geçer.
  * ⚡ **Animasyon Hızı:** `0.25x` – `3x` + manuel FPS.
  * 🎨 **Renk Modları:** Saf Beyaz, Krem, Matrix Yeşili, Amber CRT, Cyberpunk Neon, Pastel Lavanta, Buz Mavisi, Sakura, Altın, Gökkuşağı ve Özel Hex Renk Seçici.
  * ✨ **Efektler & Parçacıklar:** Kar yağışı, yağmur, şimşekli fırtına, buhar, kalpler, kıvılcımlar, yıldız tozu, uyku `Zzz` baloncukları, göz kırpma, **👀 Fare İmlecinin Yönüne Bak**, yatay aynalama (`Flip`), yumuşak neon parıltı (`Glow`) ve her zeminde okunabilirlik sağlayan gölge/kontur (`Shadow`).
  * 👻 **Ders / Hayalet Modu (Click-Through):** Açıldığında widget altındaki PDF veya tarayıcıya tıklamanıza izin verir. *(Çıkmak için sağ alttaki **Sistem Tepsisi** ikonuna sağ tıklayıp kapatabilirsiniz.)*
* **Sistem Tepsisi (Tray):** **📌 Masaüstü Düzeni (Profiller)** ile hazır/özel çoklu widget yerleşimlerini tek tıkla yükleyip kaydedin ve **🔄 Açılışta Son Açık Widget'ları Geri Yükle** seçeneğini yönetin.
* **Terminal Hub Kısayolları:** `F` tuşuyla **⭐ Favoriler** sekmesine ekleyin, `C` tuşuyla önizleme temasını canlı değiştirip masaüstüne fırlatın.
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
    "chars": ["*", ".", "+", "o"]
  },
  "frames": [
    "   .--.    \n .-(    ). \n(___.__)__)",
    "   .--.    \n .-(    )~ \n(___.__)__)"
  ]
}
```

Desteklenen `particles.type` değerleri: `"none"`, `"snow"`, `"rain"`, `"lightning"`, `"steam"`, `"hearts"`, `"sparks"`, `"stars"`.
