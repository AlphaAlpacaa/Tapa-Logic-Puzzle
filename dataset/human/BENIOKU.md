# İnsan tasarımı bulmacalar

Bu klasör, üreticinin çıktısından **ayrı** tutulur. Gerekçesi şu soru:
üretilmiş veriyle eğitilen bir model, insan tasarımı bulmacalarda ne yapıyor?
İki kümeyi karıştırmak bu soruyu cevaplanamaz hale getirir.

## Bulmaca ekleme

Kaynak dosya, satır başına bir bulmaca:

```
36 | 7x5/....../...
37 | 8x8/....../...
```

Sonra:

```bash
python -m tools.import_human dataset/human/kaynak.txt --name "kitap adı"
```

Araç her bulmacayı çözücüden geçirir ve yalnızca **tek çözümlü** olanları
kabul eder. Çözümsüz ya da çok çözümlü çıkanlar reddedilir; bu neredeyse her
zaman bir okuma ya da yazma hatasına işaret eder.

## Kısa kod yazarken dikkat

En sık yapılan hata hücre saymak. Parantezli çok sayılı ipucu **tek** hücre
sayılır:

```
(11)...(11)   →  1 + 3 + 1 = 5 hücre
```

Satır sayısı ve her satırdaki hücre sayısı başlıktaki `satırxsütun` ile
birebir tutmalı. Araç tutmazsa açıkça söyler.

## Telif

Bu klasöre konan bulmacalar başkasının eseri olabilir. İstatistik çıkarmak ve
üreticiyi onlara bakarak iyileştirmek sorun değil; bulmacaların kendisini
yeniden dağıtmak başka bir şeydir. Kaynak eser telifliyse bu klasörü dağıtıma
dahil etmeyin.
