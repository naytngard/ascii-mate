# Üçüncü taraf içerik

Bu depoda **model dosyası yoktur**. Aşağıdaki 3B modellerden yalnızca bizim ürettiğimiz ASCII HD kareler
(`assets/animations/**/*.ascii.hd` + `.ascii.json`) bulunur. Modeller `tools/models_cache/` altına indirilir
(`.gitignore`'da), `tools/blender_prep.py` ile hazırlanır, `tools/scenes/mesh_scenes.py` ile çizilir.
Lisansların hepsi sayfada CC0 / kamu malı olarak yazılıdır (kontrol: 2026-11). CC0 atıf gerektirmez; şeffaflık için listelenmiştir.

| Varlık kimliği | Model | Yazar | Kaynak | Lisans |
|---|---|---|---|---|
| `knight_sitting_3d`, `hd_knight_resting` | Knight statue (`knight_statue.blend`, kaide silindi, rengi değiştirildi) | yd | https://opengameart.org/content/knight-statue | CC0 |
| `sentinel_robot_3d` | LowPoly Robot (`Robot.obj`) | Quaternius | https://quaternius.itch.io/lowpoly-robot | CC0 1.0 |
| `dragon_baby_3d` (adı "HD Ejderha"; id aynı kaldı) | Cethiel's Dragon 3D (`dragon.obj` + `dragon.png`; dokudan köşe rengi örneklendi, kanatsız statik mesh) | Drummyfish (Cethiel ile) | https://opengameart.org/content/cethiels-dragon-3d | CC0 |
| `astronaut_eva_3d` | Astronaut low poly (`Astronaut01.fbx`, tek renk) | ThunderWare games | https://mariusmopar.itch.io/astronaut-low-poly | CC0 |

Her varlığın `.ascii.json` dosyasında `source` ve `model_credit` (başlık, yazar, URL, lisans) alanları bulunur.
`tests/test_hd_content.py` lisansın izinli kümede olmasını, künyenin bu dosyada listelenmesini ve depoda
`.obj/.fbx/.blend/.mtl/.glb` bulunmamasını denetler.
