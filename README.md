# ✨ ASCII Mate (Yüzen Masaüstü ASCII Arkadaşı)

Ders çalışırken, kod yazarken veya kitap okurken masaüstünüzde PDF'lerin, VS Code'un ve pencerelerin **tam üzerinde** hiçbir arkaplan veya çerçeve olmadan süzülen, tamamen saydam, sürüklenebilir, büyütülebilir **137 animasyon**: 134 saf klasik ASCII / canlı 3B Shader (35 canlı 3B model) + 3 opsiyonel **HD renkli ASCII** örneği (tüm karakterler ve zamanlayıcı etiketi saf ASCII'dir).

> **Platform:** ASCII Mate **yalnızca Windows 10/11** için tasarlandı (saydam tepsi widget'ı, named-pipe IPC, ekran kilidi/tam ekran algısı, akıllı okunabilirlik Windows API'lerine dayanır).

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

# Tüm 137 animasyonu (3 HD dahil) doğrular (saf klasik ASCII, hizalama, kare zıplaması, 3B shader testi):
python tests/validate_library.py

# Birim testleri (pytest; requirements-dev.txt):
python -m pytest tests -q

# Bir animasyonu terminalde önizle / statik animasyonların kontak sayfasını üret / CPU ölçümü:
python tests/preview_art.py cat_bust_3d --w 64 --h 30 --color
python tests/contact_sheet.py
python tests/bench_render.py          # klasik 3B
python tests/bench_render.py --hd     # HD senaryoları (CPU + RAM)

# Kendi görselinizi/GIF'inizi/OBJ'nizi HD varlığa çevirin (aşağıya bakın):
python tools/hd_convert.py foto.png --out assets/animations/community --id portre --cols 180
```

### 3. Python Kurmadan Çalıştırmak İçin `.exe` Oluşturma
Klasördeki **`build_exe.bat`** dosyasına çift tıklayın (`--onedir`). İki program üretir: konsolsuz **`ASCII_Mate.exe`** (tepsi + widget'lar) ve Terminal Hub için konsollu **`ASCII_Mate_CLI.exe`**. Geliştirme bağımlılıkları (`pyinstaller`, `pytest`) `requirements-dev.txt` içindedir.

---

## 📁 Proje Klasör Yapısı
```text
ascii_mate/
├── baslat.bat                  # Tek tıkla başlatıcı
├── build_exe.bat               # Taşınabilir uygulama derleyici (--onedir)
├── ASCII_Mate.spec             # PyInstaller yapılandırması
├── main.py                     # Ana giriş noktası
├── config.example.json         # Örnek ayar (gerçek config.json git'e girmez)
├── requirements.txt / requirements-dev.txt
├── README.md
├── src/
│   ├── core/                   # Modeller, 3B shader motoru, parçacıklar, kütüphane
│   ├── gui/                    # Saydam widget, sağ tık menüsü, ayarlar, sistem tepsisi
│   └── cli/                    # Terminal Hub ve canlı önizleme
├── tools/generate_model_assets.py  # 3B model JSON'larını üretir
├── tools/hd_convert.py         # görüntü/GIF/klasör/OBJ → HD (3.0) varlık
├── tools/make_hd_samples.py    # 3 örnek HD varlığı üretir (kendi ürettiğimiz kaynaklar)
├── assets/
│   ├── animations/             # Kategorilere ayrılmış saf ASCII .ascii.json dosyaları
│   └── themes.json
└── tests/                      # validate_library, pytest, bench_render, preview_art, contact_sheet
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

## 👁️ Akıllı Okunabilirlik ("Yazıların Arkasına Geç")

Sağ tık → **Yazıların Arkasına Geç** (varsayılan **kapalı**). Widget, altındaki ekran yazı içeriyorsa o hücrelerde soluklaşır ve rengini arka planın zıddına kaydırır; yazı olmayan yerde normal görünür.

> **Not:** Widget her zaman üstte duran bir overlay'dir; gerçekten başka pencerenin "arkasına" geçemez. Bu mod, yazı olan hücrelerde widget'ı **soluk / zıt renkli** yapar.

* **Nasıl çalışır (OCR yok, dilden bağımsız):** widget'ın altındaki bölge ~1,4 Hz'de yakalanır, yüksek frekans enerjisi karakter hücresi ızgarasına indirgenir, yazıya benzeyen hücreler bulunur; geçişler EMA ile yumuşatılır (titreme yok). Ekran içeriği değişmediyse analiz atlanır.
* **Kendi penceresini görmez:** `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` (Windows 10 2004+).
* **Ayarlar:** Hassasiyet ve soluklaşma düzeyi (sağ tık menüsü / İnce Ayar Paneli). Tıklama-geçirgen (hayalet) modla birlikte çalışır.
* **🔒 Gizlilik:** Ekran yakalama **yalnızca bu mod açıkken** yapılır. Yakalanan görüntü **yalnızca bellekte** işlenir, **diske yazılmaz ve ağa gönderilmez**; yalnızca hücre başına "yazı var/yok" ve ortalama parlaklık bilgisi tutulur. Mod açıkken ASCII Mate widget'ları ekran görüntüsü/kayıt uygulamalarında da görünmez (yakalamadan hariç tutulurlar); mod kapanınca eski haline döner.
* **Performans:** ≈ 17 ms/yoklama (≈ %2,5 tek çekirdek; 4 çekirdekte ≈ %0,6). OCR/UI Automation (V2) henüz uygulanmadı.

---

## 🖼️ HD Mod (Yüksek Çözünürlüklü Renkli ASCII) — opsiyonel

Normal widget'lardan ayrı bir varlık türüdür (`schema_version: "3.0"`, `"hd": true`; menülerde **[HD]** rozeti). Yüzlerce sütunluk, **karakter başına RGB renkli** ASCII çizer; koyu/arka plan hücreleri karakter koymaz (saydam kalır, masaüstünde zemin yok). Mevcut 1.0/2.0 animasyonlara ve shader'lara dokunmaz.

* **Varsayılan kapalı:** ilk HD widget açılırken "daha fazla CPU/RAM kullanır" uyarısı ve onay istenir (tepsi → *HD Mod* ile de açılıp kapatılır). **Aynı anda en fazla 2 HD widget** açılabilir (3.'de uyarı).
* **Sağ tık → HD Kalite:** Düşük (sütun/satır yarıya iner, ≤8 FPS), Orta (tam çözünürlük, ≤12 FPS), Yüksek (tam çözünürlük, ≤15 FPS) ve **HD FPS üst sınırı** (4 / 8 / 10 / 15 / otomatik). Döner HD hiçbir koşulda 15 FPS'i aşmaz.
* **Çizim hattı:** 95 ASCII glifi bir kez maskeye çizilir (NumPy glyph atlası); kare, **yalnızca değişen hücreler** tek bir `QImage` tamponuna yazılır ve `paintEvent` tek `drawImage` yapar (`drawText` yok). Kare değişmediyse hiç çizilmez; durağan HD yalnızca 2 Hz'de uyanıp hiçbir şey yapmaz. Pil tasarrufu, ekran kilidi, tam ekran uygulama ve gizli widget'ta duraklama mevcut mekanizmayı kullanır. **Akıllı okunabilirlik** HD ile de çalışır (hücre başına soluklaşma/zıt renk maskesi).
* **Depolama:** `<id>.ascii.json` (küçük üst veri: `id, name, category, cols, rows, default_fps, frame_count, bg_mode, hd_file`) + `<id>.ascii.hd` (kare başına zlib; ASCII kodları + düzlemsel RGB). Kareler **tembel** çözülür; bellekte en fazla 3 kare tutulur (ham kare dizisi hiç saklanmaz). Topluluk klasörüne **iki dosyayı birlikte** kopyalayın (sürükle-bırak yalnızca klasik varlıklar içindir).
* **Gereksinimler:** `numpy` (`requirements.txt`). Paketli sürümde numpy ≈ +26,5 MB ekler (`ASCII_Mate` klasörü 142 MB, iki exe dahil).

### Dönüştürücü: `tools/hd_convert.py`
```bash
python tools/hd_convert.py foto.png   --out assets/animations/community --id portre --cols 180 --gamma 0.8 --edge-boost 0.5
python tools/hd_convert.py anim.gif   --out assets/animations/community --id anim   --cols 160 --fps 10
python tools/hd_convert.py kareler/   --out assets/animations/community --id seri   --frames 48
python tools/hd_convert.py model.obj  --out assets/animations/community --id donen  --frames 48 --rotate-y 360 --tilt 20 --obj-color "#d8b45a"
```
`--cols`, `--ramp` (`auto` ya da kendi karakterleriniz), `--gamma`, `--edge-boost` (Sobel kenarları `| - / \`), `--bg-threshold`, `--color-lift`, `--fps`, `--frames`. Karakterler yalnızca ASCII'dir; yoğunluk rampası, widget'ın kullandığı yazı tipiyle **ölçülen gerçek mürekkep yoğunluğuna** göre sıralanır. OBJ'ler (köşe renkleri desteklenir) ortografik z-buffer ile döndürülüp aynı hattan geçirilir. Kendi CC0 şövalye/at mesh'inizi veya görüntünüzü doğrudan bu araca verebilirsiniz.

### Örnek varlıklar ve lisans
Üç örnek **tamamen bu depodaki `tools/make_hd_samples.py` betiğiyle üretilir**; harici görsel, mesh veya başkasının çizimi kullanılmamıştır:
| Varlık | Kaynak | Özellik |
|---|---|---|
| `hd_torus_knot_spin` | parametrik torus düğümü (betik OBJ üretir) → `hd_convert` | 150×75, 48 kare, 15 FPS döner |
| `hd_poppy_field` | procedural çimen + gelincik (rüzgâr) | 190×44, 24 kare, 10 FPS |
| `hd_portrait_static` | QPainter ile çizilmiş stilize portre | 130×81, durağan |

Üretilen tüm veriler proje lisansı altındadır (CC0'a eşdeğer serbest kullanım). Örnekler motorun kalite çıtasını göstermek içindir; fotoğraf kalitesinde şövalye/at gibi içerik için kendi CC0 kaynağınızı dönüştürün.

### HD performans ölçümleri
`python tests/bench_render.py --hd` ile ölçüldü (Windows 11, offscreen Qt, tek çekirdek tahmini; gerçek DWM/ekran birleştirme maliyeti dahil değil). "CPU" = tick + `paintEvent` süresi ÷ zamanlayıcı aralığı. 4 çekirdekli makinede toplam CPU ≈ değer ÷ 4.

| Senaryo | Kalite | Aralık | ms/tick | CPU (tek çekirdek) | +RAM (widget) |
|---|---|---|---|---|---|
| Durağan portre | herhangi | 500 ms | ≈0 | **%0,0** | ≈4–8 MB |
| Hafif hareketli çimen/gelincik (10 FPS) | Orta/Yüksek | 100 ms | ≈1,9 | **%1,9** | ≈3–5 MB |
| Aynı | Düşük (≤8 FPS) | 125 ms | ≈2,5 | %2,0 | ≈4 MB |
| Dönen torus düğümü | Düşük (≤8 FPS) | 125 ms | ≈5,9 | %4,7 | ≈6 MB |
| Aynı | Orta (≤12 FPS) | 83 ms | ≈5,7 | %6,9 | ≈4–5 MB |
| Aynı | Yüksek (15 FPS) | 67 ms | ≈5,6 | %8,4 | ≈5 MB |

Karşılaştırma için klasik canlı 3B shader (kedi, 12 FPS): ≈ %8 tek çekirdek. İki HD widget açıkken tepsi sürecinin toplam çalışma kümesi ≈ 147 MB (Qt dahil) ölçüldü. Hız optimizasyonu öncesi (alan başına `drawText`/çoklu çarpma yolu) dönen torus ≈ %14,3'tü; kanal başına bitişik çarpma ve bitişik blok yazımı ile ≈ %8,4'e indi.

---

## 🔋 Performans İpuçları

* 3B shader'lar varsayılan olarak **en çok 15 FPS** (hayvan modelleri 12 FPS) çalışır; **İnce Ayar Paneli → Manuel FPS** ile değiştirin. Daha düşük FPS ve daha küçük ızgara (`Kompakt`) CPU'yu doğrudan azaltır.
* Gölge tek geçiştir; **Glow varsayılan kapalıdır** (ek çizim geçişi).
* Ekran **kilitliyken** çizim durur; tam ekran bir uygulama widget'ın bulunduğu ekranı kaplıyorsa ve widget "Her Zaman Üstte" değilse durur. **Pildeyken** FPS otomatik ~%40 düşer (tepsi menüsünden kapatılabilir).
* Statik animasyonlar yalnızca kare/parçacık/zamanlayıcı gerektiğinde 1–8 FPS'te güncellenir.
* Hata günlükleri: `%APPDATA%\ASCII_Mate\logs\ascii_mate.log` (dönen dosya).

---

## 🧩 Kütüphane Kuralları

* Aynı `id` iki dosyada varsa **yerleşik animasyon kazanır**; topluluk dosyası yerleşik olanı ezmez (uyarı log'a yazılır). Aynı türden iki dosya çakışırsa alfabetik yolda ilk görülen kalır.
* Aynı animasyonun birden fazla kopyası açılabilir; her kopya **kendi konum/ayarını** saklar (`id`, `id#2`, ...). Zamanlayıcı süresi kayıtlıdır ama **kendiliğinden başlamaz**.
* IPC (Terminal Hub ↔ tepsi host'u) kullanıcıya özel bir `authkey` ile korunur (`%APPDATA%\ASCII_Mate\ipc.key`).

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

İsteğe bağlı `"blink_patterns": [["o.o", "-.-"]]` alanı, göz kırpma efektinde bu animasyona özel değişimleri tanımlar (aynı uzunlukta metin çiftleri). Verilmezse yalnızca göz benzeri bağlamlarda eşleşen güvenli varsayılanlar kullanılır.

Desteklenen `particles.type` değerleri: `"none"`, `"snow"`, `"rain"`, `"lightning"`, `"steam"`, `"hearts"`, `"sparks"`, `"stars"`.
