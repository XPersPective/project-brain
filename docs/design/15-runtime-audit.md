# Kaynak denetimi — 18 Ekim 2026

Sonraki yayın: bu düzeltmeler 3.2.1'e alındı. Kurulu kopyalar ve paket hakkındaki
aşağıdaki notlar ilk denetim anını anlatır; güncel durum [teslim kaydındadır](12-final-delivery.md).

İstek: "Projeyi baştan sona bir incele. Hataları düzelt."

İnceleme kaynak skill, teslim kayıtları ve runtime akışları üzerinden yapıldı:
görev/kanıt/kabul, onay ve iş rezervasyonu, CLI keşfi/yönlendirme/kota,
migration ve arşivli aktarım. Kaynak deponun tamamlanmış geçici planı yeniden kurulmadı.
Başlangıç çalışma ağacı temizdi; mevcut tam test paketi geçti.

## Düzeltilen bulgular

1. **Yüksek: eksik kota yanıtı rezerv korumasını kaldırabiliyordu.**
   Özel sorguda alanın bulunması yeterli sayılıyordu: haftalık değer `null`,
   `quota_windows: []` veya listeden haftalık pencerenin çıkarılması önceki düşük
   kotayı silebiliyordu. Codex scan/refresh doğrudan aynı veriyi güncelliyordu.
   Üç çağıran artık aynı güncelleme kontrolünü kullanıyor. Önceden ölçülmüş pencere
   kaybolursa son değer ve zamanı korunuyor, yanıt `invalid` sayılıyor. Tam ve güncel
   yanıtta kota yükselmesi normal şekilde kabul ediliyor.
2. **Yüksek: OmniRoute chat kodlama işçisi değildi.**
   Bu makinedeki kurulu `omniroute/bin/cli/commands/chat.mjs` incelendi: tek metin
   isteği gönderip yanıt yazıyor; depo okuma/düzenleme veya araç çalıştırma döngüsü
   yok. Başarılı süreç çıkışı implementasyon kanıtı değildir. Yerleşik chat adaptörü
   kaldırıldı; açık kodlama-ajanı adaptörü olmadan worker seçimine girmiyor.
   Katalog keşfi korunuyor. Mevcut özel `worker_argv` mekanizması kullanılabilir;
   yeni bağımlılık, yönlendirici kurulumu veya sessiz model değişimi eklenmedi.
3. **Orta: OmniRoute başlangıcı süre bütçesini aşıyordu.**
   İlk sağlık sorgusu ve süreç beklemesinden sonra timeout yeniden başlatılıyordu;
   sonunda ek sağlık sorgusu yapılıyordu. Artık tüm aşamalar tek monotonic son zamanı
   paylaşıyor. Bu, OS süreç oluşturma/DNS süreleri için mutlak gerçek zaman garantisi değildir.
4. **Orta: adaptör placeholder genişletmesi prompt'u bozabiliyordu.**
   `{prompt} / {model}` şablonunda prompt içindeki literal `{model}` de ikinci
   turda değişiyordu. Tek geçişli regex substitution ile yerleştirilen kullanıcı
   metni tekrar şablon olarak yorumlanmıyor.

Regresyonlar mevcut `test_economy.py` içine eklendi; yeni framework yok.

## Doğrulama ve sınırlar

- `python -u skills/project-brain/scripts/test_brain.py`: son runtime değişikliklerinden
  sonra çıkış 0; economy ve discovery dahil tüm alt paketler geçti.
- `test_economy.py`: odak kontrolleri geçti.
- 16 Python dosyası Python 3.8 dilbilgisiyle ayrıştırıldı; yeni runtime bağımlılığı yok.
- CLI sürümü 3.2.0 / şema 4; kaynak depoda `boot` beklenen `NO_BRAIN` durumunu veriyor.
- `git diff --check`: geçti.
- Testler Windows üzerinde geçici depolar, yerel süreçler ve sahte metadata yanıtları
  kullanır. Ücretli inference, gerçek hesap kota tüketimi ve her provider'ın canlı
  uçtan uca çalışması bu denetimin kanıtı değildir.
- Python 3.8/POSIX üzerinde gerçek çalıştırma, Z.AI canlı kota ve eksik CLI kurulum/
  giriş akışı önceki teslimdeki gibi ayrıca doğrulama gerektirir.
- Bu incelemede bağımsız ikinci ajan incelemesi yapılmadı. Kanıt hash'leri kaliteyi
  veya gözlem doğruluğunu tek başına ispatlamaz; her olası senaryoya kusursuzluk iddiası yoktur.
- `dist/project-brain-3.2.0.zip` tarihsel sürüm paketidir; bu yayınlanmamış kaynak
  düzeltmelerini içermez. Global kurulu skill kopyaları güncellenmedi.
