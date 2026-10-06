# Tapa — kural motoru (1. aşama)

Akıl oyunu platformunun çekirdeği. Bu aşamada yalnızca **kural motoru** hazır:
değişken boyutlu ızgara, ipucu yerleştirme, kural doğrulama ve bulmaca
saklama. Arayüz, çözücü, üretici ve yapay zeka katmanları bunun üzerine gelecek.

## Çalıştırma

Hiçbir bağımlılık yok, saf Python (3.10+):

```bash
python demo.py            # kullanım örneği
python -m tests.test_engine   # testler
```

## Mimari

```
tapa/
├── engine/           ← saf Python, bağımlılıksız çekirdek
│   ├── board.py      ızgara, hücre durumları, ipucu katmanı
│   ├── rules.py      halka okuma, blok deseni, 2x2, bağlantılılık, çıkarımlar
│   ├── validator.py  tam çözüm ve canlı (kısmi) doğrulama
│   └── serialize.py  JSON kütüphanesi + tek satırlık kısa kod
├── tests/
├── puzzles/          ← bulmaca kütüphanesi (.json)
└── demo.py
```

Motor arayüzden tamamen bağımsızdır. Aynı paket hem FastAPI sunucusunun hem de
ileride RL/CNN eğitim döngüsünün içinden çağrılacak; model eklerken arayüze
dokunmaya gerek kalmayacak.

## Uygulanan kurallar

| | Kural | Nerede |
|---|---|---|
| K1 | İpucu hücreleri boyanmaz | `Board.set_cell` engeller |
| K2 | 8 komşunun saat yönünde okunan dolu blok uzunlukları = ipucu sayıları (döngüsel, sıra önemsiz, bloklar arası en az bir boşluk, ızgara dışı = boş) | `rules.runs_pattern` |
| K3 | 2x2 tamamen dolu alan yasak | `rules.square_violations` |
| K4 | Dolu hücreler tek ortogonal bağlı grup | `rules.wall_is_connected` |

İpucular yerleştirilirken geometrik olarak imkânsız olanlar reddedilir —
örneğin köşe hücresine `4` konamaz, çünkü orada yalnızca 3 komşu vardır.

## İki doğrulama modu

- `validate_solution(board)` — bitmiş çözümü değerlendirir. Belirsiz hücreler
  boş sayılır; `strict=True` ile her hücrenin işaretlenmesi zorunlu kılınabilir.
- `validate_partial(board)` — yalnızca geri dönüşü olmayan çelişkileri
  raporlar. Oyuncuya anlık geri bildirim vermek ve çözücüde dalı budamak için.

Her iki mod da `ValidationResult` döndürür; `result.error_cells` doğrudan
arayüzde kırmızıya boyanacak hücreleri verir.

## Bulmaca formatları

**JSON** kanonik saklama (meta veri ve isteğe bağlı çözüm taşır):

```json
{"format": "tapa-puzzle", "version": 1, "rows": 6, "cols": 6,
 "clues": [{"r": 1, "c": 1, "values": [3]}], "meta": {"zorluk": "kolay"}}
```

**Kısa kod** hızlı giriş ve paylaşım için:

```
6x6/....../.3..(11)./....../....../..0.../......
```

`.` ipucusuz hücre, tek rakam tek sayılı ipucu, parantez çok sayılı ipucu.
Kendi bulmacanı `from_code("...")` ile tek satırda ekleyebilirsin.

## Yapay zeka için hazırlık

Motor şimdiden model geliştirmeye uygun yüzeyler sunuyor:

- `board.grid_snapshot()` / `board.apply_grid()` — tahtayı düz int matrisi
  olarak alıp verir; CNN girdisi ve RL gözlemi için doğrudan kullanılabilir.
- `rules.clue_candidates()` — bir ipucunun kalan tüm olası boyamaları.
  Kısıt yayılımının, CP-SAT kodlamasının ve ödül tasarımının temeli.
- `rules.forced_cells()` — tek adımlık mantıksal çıkarım. Hem "ipucu ver"
  özelliği hem de RL ajanına karşılaştırma tabanı (baseline) olur.
- `board.copy()` — ucuz durum kopyalama; arama ve simülasyon için.

## Sırada ne var

1. Çözücü: önce mantıksal yayılım + geri izleme, sonra CP-SAT karşılaştırması
2. Üretici: tek çözümlü bulmaca üretimi (çözücüye bağımlı)
3. FastAPI + React arayüzü
4. AI katmanı: Gym uyumlu ortam, CNN ve RL modelleri

---

# Arayüz (2. aşama)

FastAPI sunucusu + React (Vite, TypeScript) istemcisi. Kural mantığının tamamı
Python'da kalır; React yalnızca çizim ve etkileşimden sorumludur. Aynı kuralın
iki ayrı yerde yazılması (ve zamanla birbirinden ayrışması) böylece engellenir.

## Çalıştırma

İki terminal gerekiyor.

```bash
# 1. terminal — sunucu
pip install -r requirements.txt
uvicorn api.main:app --reload          # http://127.0.0.1:8000/docs

# 2. terminal — arayüz
cd web
npm install
npm run dev                            # http://localhost:5173
```

Vite, `/api` isteklerini sunucuya kendisi yönlendirir; istemci kodunda sunucu
adresi hiç geçmez. Tek adrese indirmek istersen `cd web && npm run build`
çalıştırman yeterli — sunucu `web/dist` klasörünü görürse arayüzü de kendisi
servis eder ve her şey `http://127.0.0.1:8000` altında toplanır.

## API

Sunucu **durumsuzdur**: oyun durumu istemcide durur, her istekte tahtanın
tamamı gönderilir. Bu kasıtlı — aynı uç noktalar, oturum yönetimi olmadan toplu
değerlendirme ve model eğitimi için de kullanılabilir.

| Uç nokta | İş |
|---|---|
| `GET /api/puzzles` | kütüphaneyi listeler |
| `GET /api/puzzles/{id}` | bulmacayı açar |
| `POST /api/puzzles/from-code` | kısa koddan bulmaca kurar |
| `POST /api/puzzles/blank` | boş ızgara |
| `POST /api/validate` | `mode: partial` anlık uyarı, `mode: solution` bitiş kontrolü |
| `POST /api/hint` | kesin çıkarılabilen tek hücreyi gerekçesiyle verir |

## Arayüzde ne var

- Sol tık duvar örer, sağ tık "kesin boş" noktası koyar; her ikisi de sürükleyerek çalışır
- Klavye: ok tuşları, boşluk doldurur, `x` nokta koyar, `Ctrl+Z` geri alır
- Anlık uyarı (açılıp kapanabilir): yalnızca geri dönüşü olmayan çelişkileri gösterir
- "Bir hücre göster": tek adımlık mantıksal çıkarımı gerekçesiyle uygular
- Kısa kod yapıştırarak kendi bulmacanı açma
- **Çözüm kaydı**: her hamle zaman damgasıyla kaydedilir, JSON olarak indirilebilir

Son madde ileriye dönük: insan çözüm süresi verisi sonradan toplanamaz, bu
yüzden en baştan kaydediliyor. Hem zorluk ayarı hem de insan çözücü modellemesi
bu veriye dayanacak.

## Tasarım kararı: duvarın sürekliliği

Bitişik iki dolu hücre arasındaki ayırıcı çizgi duvarın rengine boyanır
(`join-right` / `join-down`). Duvar tek bir sürekli şekil olarak görünür,
böylece K4 bağlantılılık kuralı bakar bakmaz okunur. Süsleme değil, kuralın
görselleştirilmesi.

## Bulmaca kütüphanesi

`puzzles/` içindeki bulmacalar üretici tarafından kuruluyor (4. aşamaya bakın).
Geçici `tools/make_puzzles.py` aracı silindi.

---

# Çözücü (3. aşama)

Bağımlılıksız, saf Python. İki parça: kesin çıkarım teknikleri (yayılım) ve
tıkandığında devreye giren arama.

```bash
python -m tests.test_solver
```

## Teknikler kayıtlı listede

`engine/solver.py` içindeki `TECHNIQUES` listesi ucuzdan pahalıya sıralıdır.
Her teknik bir isim, bir seviye ve bir fonksiyondan ibarettir; yeni çıkarım
eklemek listeye bir satır yazmaktır, çözücüyü değiştirmek değil.

| Seviye | Teknik | Ne yapar |
|---|---|---|
| 1 | ipucu okuma | İpucunun kalan tüm olasılıklarında aynı kalan komşular |
| 2 | 2x2 kuralı | Bir 2x2 bloğun üçü doluysa dördüncüsü boştur |
| 2 | ipucu + 2x2 | 2x2 oluşturan olasılıklar elendikten sonra kalan zorunluluklar |
| 3 | ulaşılmaz bölge | Duvara hiçbir yoldan bağlanamayacak hücreler boştur |
| 3 | bağlantı boğazı | Boşaltılırsa duvarı kopartacak hücreler doludur |
| 4 | çelişkiyle çıkarım | Varsayım kurulup çürütülerek kanıtlanan hücreler |

## Çelişkiyle çıkarım kör tahmin değildir

Dördüncü seviye, insan çözücülerin zor bulmacalarda yaptığı şeyin karşılığı:
"bu hücre dolu olsaydı ne olurdu?" diye varsayılır, ucuz teknikler sonuna kadar
yayılır, çelişkiye varılırsa hücrenin boş olduğu **kesin** olarak bilinir.

Aradaki fark önemli. Kör tahmin bir hücreyi rastgele seçip ilerlemektir;
sonucu belirsizdir ve bulmacayı adaletsiz yapar. Çelişkiyle çıkarımın sonucu
ise belirlenmiştir — kanıt tamamlandığında geriye tek olasılık kalır. Bu yüzden
4. seviye bulmacalar hâlâ tek çözümlü ve adildir, yalnızca daha derin akıl
yürütme isterler.

Varsayımın içinde varsayım kurulmaz (`DEDUCTION_LEVEL = 3`): hem sonsuz
özyineleme engellenir hem maliyet sınırlanır. Aramanın düğümlerinde de bu
teknik çalıştırılmaz (`SEARCH_LEVEL = 3`), çünkü arama zaten dallanıyor.

Her tekniğin tek bir sözü var: döndürdüğü hücre, mevcut bilgiyle **kesin**
olmak zorunda. Tahmin yok — tahmin aramanın işi.

Yayılım her turda en ucuz tekniğe geri döner. Pahalı bir teknik bir hücre
açtıysa ucuz teknikler yeniden iş görebilir; ayrıca bir bulmaca ancak gerçekten
gerekiyorsa üst seviye olarak işaretlenir.

## Zorluk ölçümü

`solver.rate(board)` bulmacayı çözmek için gereken en pahalı tekniğe bakar:

- yalnızca seviye 1 → kolay
- seviye 2 gerekiyorsa → orta
- seviye 3 gerekiyorsa → zor
- seviye 4 (çelişkiyle çıkarım) gerekiyorsa → çok zor
- bunlar da yetmiyor, kör tahmin şartsa → adil değil (üretici bunları atar)

### Etkin seviye: "gerekti" ne demek

Etiket, en pahalı tekniğin *bir kez* kullanılmasına bakmaz. Bir bulmaca ancak o
seviyedeki teknikler yeterince çok hücre açtıysa o seviyeden sayılır
(`MIN_USES`: seviye 3 için en az 2, seviye 4 için en az 3 hücre). Sebebi
pratik: tek bir hücre için çelişki kurmayı gerektiren bulmacayı oyuncu o adımı
fark etmeden de çözer, dolayısıyla "çok zor" demek yanıltıcı olur.

İnsan çözüm süreleriyle kalibre edilmediği sürece bu bir *sıralama* ölçüsüdür,
mutlak bir zorluk değeri değil — arayüzün topladığı hamle kayıtları tam da
bunun için duruyor.

## Sağlamlık testi

`test_deductions_are_sound` en kritik test. Hatalı bir teknik çelişki üretmek
yerine sessizce yanlış hücre yerleştirir ve bu hata üreticiye, oradan bulmaca
kütüphanesine sızar. Test, bilinen çözümden türetilmiş rastgele bulmacalarda
her çıkarımı gerçek çözümle karşılaştırır — bulmaca birden çok çözümlü olsa
bile geçerli bir ölçüt, çünkü kesin bir çıkarım tüm çözümlerde doğru olmalıdır.

## Yeni uç noktalar

| Uç nokta | İş |
|---|---|
| `POST /api/solve` | bulmacayı sıfırdan çözer, çözüm tek mi söyler |
| `POST /api/difficulty` | zorluk etiketi ve kullanılan teknik dökümü |

`POST /api/hint` artık çözücünün teknik zincirini kullanıyor; gerekçe olarak
hangi tekniğin devreye girdiğini açıklıyor.


---

# Üretici ve veri kümesi (4. aşama)

```bash
# 100 bulmaca, 6x6 ile 12x12 arası, tüm zorluklar
python -m tools.build_dataset --count 100

# sadece büyük ve çok zor olanlardan 20 tane ekle
python -m tools.build_dataset --count 20 --min-size 12 --max-size 16 --levels 4

# seyrek duvarlı kolay bulmacalar
python -m tools.build_dataset --count 30 --levels 1,2 --densities 0.35,0.45

# belirli boyutlar
python -m tools.build_dataset --count 40 --sizes 8,10,14

python -m tests.test_generator
```

Her çalıştırma mevcut veri kümesinin **üstüne ekler**: eski kayıtlar okunur,
yenileri sonuna yazılır, tekrarlar atlanır. Sıfırdan başlamak için `--fresh`.

| Seçenek | İş |
|---|---|
| `--count` | kaç bulmaca üretilsin |
| `--min-size` / `--max-size` | kenar uzunluğu aralığı |
| `--sizes` | boyutları doğrudan ver (`8,10,14`) |
| `--levels` | hedef zorluklar (`1,2,3,4`) |
| `--densities` | duvar yoğunlukları (`0.35,0.45`) |
| `--seed` | tekrarlanabilirlik; verilmezse rastgele |
| `--attempts` | bir bulmaca için en fazla kaç duvar denensin |
| `--fresh` | eklemek yerine sıfırdan başla |
| `--loose-level` | zorluğu şart koşma, daha hızlı üret |
| `--no-library` | arayüz kütüphanesine kopyalama |

## Yöntem

Oymacılık: önce geçerli bir çözüm inşa edilir, ipucular ondan türetilir, sonra
elenebilecek ipucular elenir. Tersi yön — rastgele ipucu serpip çözüm aramak —
neredeyse hep çözümsüz tahta üretir.

Duvar tek hücreden başlatılıp komşuluk üzerinden büyütülür. Bağlantılılık ve
2x2 yasağı inşa sırasında zaten sağlandığı için sonradan düzeltme gerekmez ve
duvar yoğunluğu hedeflenebilir.

## Elemenin ölçütü: mantıkla çözülebilirlik

Bir ipucu, çıkarıldığında bulmaca hâlâ **saf mantıkla** sonuna kadar
çözülebiliyorsa elenir. Bu ölçütün iki kazancı var:

1. **Adalet.** Oyuncuyu tahmine zorlayan bulmaca üretilmez.
2. **Hız.** Mantıkla sonuna kadar çözülebilen bir bulmaca zorunlu olarak tek
   çözümlüdür — yayılımın attığı her adım zaten zorunludur. Teklik için ayrıca
   arama yapmaya gerek kalmaz.

## Zorluk nasıl hedefleniyor

`max_level`, oyuncunun kullanmasına izin verilen en pahalı teknik. Düşük
seviyede eleme zorlaşır, çok ipucu kalır, bulmaca kolay olur:

| max_level | Sonuç | 8x8'de tipik ipucu sayısı |
|---|---|---|
| 1 | kolay — yalnızca ipucu okuma yeter | ~15 |
| 2 | orta — 2x2 akıl yürütmesi gerekir | ~10 |
| 3 | zor — bağlantılılık akıl yürütmesi gerekir | ~11 |
| 4 | çok zor — çelişkiyle çıkarım gerekir | ~13 |

`max_level` *izin verilen* en pahalı tekniktir; üretilen bulmaca daha ucuz
tekniklerle de çözülebiliyorsa etiketi düşük kalır. İstenen zorluğu garanti
etmek için `exact_level` (komut satırında varsayılan) devreye girer: yalnızca
gerçekten o seviyeyi gerektiren bulmacalar kabul edilir. Daha çok deneme
ister ama ne istediyseniz onu verir. `--loose-level` ile kapatılabilir.

## Çıktılar

`dataset/puzzles.jsonl` asıl veri kümesi — satır başına bir bulmaca, çözüm,
zorluk dökümü ve öznitelikler bir arada. Üretim sırasında anında yazılır.

`puzzles/*.json` arayüzün vitrini: her boyut-zorluk çiftinden bir örnek.

Çeşitlilik rastgeleliğe bırakılmıyor, planlanıyor: boyut (6-12), duvar
yoğunluğu (0.42 / 0.50 / 0.58) ve hedef zorluk (1 / 2 / 3) kombinasyonlarının
hepsinden eşit sayıda üretiliyor. Ayrıca aynı bulmaca ya da aynı **çözüm** iki
kez kaydedilmiyor; aksi hâlde eğitim ve test kümesine birlikte düşüp başarıyı
şişirirdi.

## İpucu değeri sınırı

`--max-clue` (varsayılan 5) büyük ipucu değerlerini eler. Bunun zorluk
üzerindeki etkisi doğrudan: `8` ipucusu sekiz komşunun da dolu olduğunu söyler
ve görüldüğü anda sekiz hücre birden kapanır. Büyük değerler bulmacayı anında
açar; sınırlamak hem görünümü insan tasarımına yaklaştırır hem bulmacayı
gerçekten zorlaştırır.

Aday ipucular bilgi değeri düşük olanlardan başlanarak seçilir: küçük sayılar
ve çok sayılı ipucular önde gelir. Sınırı düşürmek üretimi yavaşlatır, çünkü
uygun duvar bulmak zorlaşır.

Mevcut veri kümesinde en büyük ipucu değeri 5, çok sayılı ipucuların oranı
%31. Karşılaştırma için: sınır konmadan önce `7` ve `8` en sık çıkan değerler
arasındaydı ve çok sayılı oran %14 civarındaydı.

## Eleme doyuma kadar sürer

Bir ipucu elendikten sonra, daha önce elenemeyen bir başkası elenebilir hale
gelebilir. Bu yüzden eleme tek geçişle değil, hiçbir ipucu daha
çıkarılamayana kadar tekrarlanır. Tek geçiş gereğinden fazla ipucu
bırakıyordu.

---

# CP-SAT karşılaştırması (5. aşama)

```bash
python -m tools.benchmark              # veri kümesinde doğrula ve ölç
python -m tools.benchmark --scale      # artan boyutlarda ölçeklenme
python -m tools.benchmark --encodings  # iki bağlantılılık kodlamasını kıyasla
```

CP-SAT bir makine öğrenmesi algoritması değil; Google OR-Tools'un kısıt
çözücüsü. Veriden öğrenmez, eğitim yoktur. Yaptığı şey mantıksal aramadır ama
öğrenen bir arama: bir değer dener, çelişkiye varınca o çelişkinin *sebebini*
yeni bir kural olarak kaydeder ve aynı hataya bir daha düşmez.

Fark, `solver.py` ile karşılaştırınca net görünür. Orada Tapa'yı *nasıl*
çözeceğimizi adım adım yazdık. Burada yalnızca **ne istediğimizi** bildiriyoruz;
arama stratejisi çözücünün işi.

`ortools`, `requirements.txt` içinde. Yine de içe aktarma korumalı: paket
bulunamazsa `engine/cpsat.py` yüklenir ama `available()` False döner ve
çağrılar açık bir hata mesajı verir. Motor, arayüz ve üretici etkilenmez —
kurulum yarım kalsa bile sistemin geri kalanı çalışmaya devam eder.

## Kısıtların kodlanması

| Kural | Kodlama |
|---|---|
| K1 ipucu hücreleri boyanmaz | `x == 0` |
| K2 ipucu deseni | tablo kısıtı (`AddAllowedAssignments`) |
| K3 2x2 yasağı | her 2x2 için `toplam <= 3` |
| K4 bağlantılılık | erişilebilirlik etiketleri veya tekrarlı kesme |

İpucu kuralı en temiz oturan parça. Geçerli sekizli desenleri zaten
`rules.clue_candidates` hesaplıyor (en fazla 256 olasılık); CP-SAT'ın tablo
kısıtı bu listeyi doğrudan kabul ettiği için kural aritmetiğe çevrilmeden
aktarılıyor.

## Bağlantılılık: tasarım tahminini ölçüm çürüttü

CP-SAT'ta "şu hücreler tek parça olsun" diye hazır bir kısıt yok. İki yol
yazıldı:

**`cuts` (varsayılan).** Önce bağlantılılık olmadan çözülür; sonuç parçalıysa
"bu parça dolu ve çevresi boş" durumu yasaklanıp yeniden çözülür.

**`reach`.** Her dolu hücreye bir derinlik etiketi verilir. Tam olarak bir dolu
hücre kök olur (etiket 0); diğer her dolu hücrenin, etiketi bir eksik olan dolu
bir ortogonal komşuyu "öncül" seçmesi şart koşulur. Her dolu hücreden köke
azalan bir zincir uzanır. Akış tabanlı kodlamaya tercih edildi: büyük-M çarpımı
gerektirmiyor, hücre başına dört boole değişkeniyle sınırlı kalıyor.

Başlangıçta varsayılan `reach` seçilmişti; gerekçe, modelin eksiksiz kalması ve
teklik kontrolünün bağlantılılığı döngü dışında bırakmamasıydı. Ölçüm bunu
çürüttü: `--encodings` karşılaştırmasında `cuts` dört ila beş kat hızlı çıktı ve
**kesme turu sayısı her bulmacada sıfır** oldu. Yani ipucu ve 2x2 kısıtları
bağlantılılığı pratikte zaten zorluyor; `reach` kodlamasının eklediği
değişkenler saf maliyete dönüşüyor.

| | etiket (`reach`) | kesme (`cuts`) |
|---|---|---|
| 10 bulmaca toplam | 0.50s | 0.12s |
| gereken kesme turu | — | 0 |

`reach` yine de duruyor. Yarım bırakılmış tahtalarda (oyun ortasında ipucu
üretimi, ileride model değerlendirmesi) kısıtlar zayıfladığı için parçalı
çözümler ortaya çıkabilir; o durumda kesme turları çoğalır ve eksiksiz model
avantaja dönebilir. Bu da ölçülerek karar verilecek.

## Çözüm sayma

Bulunan her çözüm modele yasak (no-good) olarak eklenip yeniden çözülür.
CP-SAT'ın kendi "tüm çözümleri say" kipi burada kullanılamaz: erişilebilirlik
etiketleri yardımcı değişken olduğu için aynı boyama farklı etiketlerle birden
çok kez sayılırdı.

## Doğrulama

`tools/benchmark.py` yalnızca ölçmez, iki çözücüyü birbirine karşı
**doğrular**: çözümler ve çözüm sayıları karşılaştırılır. Tamamen farklı iki
yöntemin aynı cevapta buluşması, doğruluk için elimizdeki en güçlü kanıt.
Ayrışırlarsa en az biri hatalıdır ve bunu bilmek gerekir.

## Ölçeklenme testinin ayarları neden farklı

`--scale`, bulmacaları veri kümesi üretimindeki katı ayarlarla değil, gevşek
ayarlarla üretir: ipucu değerine sınır konmaz, eleme hafif tutulur, hedef zorluk
şart koşulmaz. Sebebi, bu testin amacının güzel bulmaca üretmek değil
çözücüleri büyük tahtalarda yarıştırmak olması. Katı ayarlarla 10x10 üstünde
uygun duvar bulunamıyor ve test ölçmek istediği şeye hiç ulaşamıyordu.

## İlk ölçümün okunması

Veri kümesi üzerinde mantıksal çözücü CP-SAT'tan yaklaşık dört kat hızlı çıktı
(ortalama 0.013s / 0.060s). Bu sonucu olduğundan fazla okumamak gerekir:

1. Küçük tahtalarda model kurma maliyeti baskın; asıl arama sürenin küçük bir
   parçası.
2. Daha önemlisi, karşılaştırma mantıksal çözücünün lehine kurulu. Veri
   kümesindeki her bulmaca "saf mantıkla çözülebilsin" şartıyla üretildi, yani
   bunlar mantıksal çözücünün hiç arama yapmadan bitirebildiği bulmacalar.
   CP-SAT'ın asıl gücü olan çelişki öğrenme bu örneklerde hiç devreye girmiyor:
   8x8'de 258 dallanmaya karşılık **sıfır çatışma** ölçüldü.

Adil karşılaştırma, aramanın gerçekten gerektiği örneklerde yapılmalı.

## Ölçeklenme sonucu: kesişme yok, çünkü kimse aramıyor

8x8'den 16x16'ya kadar yapılan ölçümde CP-SAT her boyutta **sıfır dallanma ve
sıfır çatışma** raporladı. Yani arama hiç devreye girmedi; bulmacaları
ön-işleme ve yayılım bitirdi. Ölçülen süre farkı algoritmaların değil, Python
tarafında model kurma maliyetinin farkı — 16x16'da 256 hücre için binlerce
kısıt nesnesi yaratılıyor.

Mantıksal çözücü için de durum aynı: veri kümesi ve ölçeklenme testindeki
bulmacalar ipucu açısından zengin olduğu için yayılım tek başına yetiyor.

Bunun asıl sebebi bağlantılılık teknikleri. "Ulaşılmaz bölge" ve "bağlantı
boğazı" o kadar çok hücre kapatıyor ki arama nadiren gerekiyor.

## Arama ne zaman gerekiyor: `--hard`

```bash
python -m tools.benchmark --hard                    # 18,22,26,30
python -m tools.benchmark --hard --keep 0.5 --sizes 26,30
```

Bu kip ipucuların yalnızca bir kısmını bırakır. Tahta eksik kısıtlandığı için
tek çözümlü olmayabilir; istenen de budur. Sorulan soru "çözümü bul" değil,
"en fazla iki çözüm say" — yani teklik kontrolü, üreticinin gerçekte ihtiyaç
duyduğu işlem.

Mantıksal çözücünün ölçülen davranışı (ipucuların %60'ı bırakılarak):

| boyut | seyrek ipucu | tam ipucu |
|---|---|---|
| 18x18 | 0.23s | 0.08s |
| 22x22 | 0.81s | 0.13s |
| 26x26 | 1.26s | 0.20s |
| 30x30 | 2.48s | 0.23s |

Tam ipuçlu sütun neredeyse düz: orada yayılım bitiriyor, boyut pek fark
etmiyor. Seyrek sütun ise hızla büyüyor — arama orada başlıyor. CP-SAT ile
anlamlı karşılaştırma bu rejimde yapılmalı.

Mantıksal çözücüye bu amaçla zaman sınırı eklendi
(`solver.solve(..., time_limit=...)`); aşıldığında `stats.timed_out`
işaretlenir ve sonuç eksik sayılır.

---

# İnsan tasarımı bulmacalar ve karşılaştırma (6. aşama)

```bash
python -m tools.import_human dataset/human/kaynak.txt --name "kitap adı"
python -m tools.analyze
```

İnsan tasarımı bulmacalar `dataset/human/` altında, üreticinin çıktısından
**ayrı** tutulur. Gerekçesi şu soru: üretilmiş veriyle eğitilen bir model,
insan tasarımı bulmacalarda ne yapıyor? İki kümeyi karıştırmak bu soruyu
cevaplanamaz hale getirir.

## Çözücü, okumanın denetçisi

`import_human` her bulmacayı çözücüden geçirir ve yalnızca tek çözümlü
olanları kabul eder. Elle ya da görüntüden girilen bir bulmacada tek bir
rakam hatası, bulmacayı neredeyse her zaman çözümsüz ya da çok çözümlü yapar.
Kusursuz bir denetim değil — hatalı bir okuma tesadüfen başka bir geçerli
bulmaca üretebilir — ama hataların büyük çoğunluğunu yakalar.

## `analyze` neyi ölçüyor

İpucu değeri dağılımı, çok sayılı ipucu oranı ve kombinasyonları, ipucu ve
duvar yoğunluğu, ve **simetri**.

Simetri ölçümü üretilmiş veri üzerinde şimdiden bir açık gösterdi:

| ölçüt | üretilmiş |
|---|---|
| tam 180° simetrik bulmaca | %0 |
| dönme eşi olan ipucu oranı | %19 (tesadüf seviyesi) |

İnsan tasarımı Tapa bulmacalarında ipucu yerleşimi genellikle dönme
simetrisine sahiptir. Üretici ipucuları tamamen rastgele yerleştiriyor,
dolayısıyla bu geleneği hiç taşımıyor. Ölçüm insan verisiyle doğrulanırsa,
üreticiye simetri hedefi eklemek görsel kalite açısından en büyük kazanç
olacak.

## Arayüzde bulmaca girme

Üst çubuktaki **Düzenle** kipi boş bir ızgara açar. İki giriş yolu var,
çünkü kitapta iki ayrı sayfa var: bulmaca sayfası ve çözüm sayfası.

### Sayılardan Hücreye tıkla ya da
oklarla gez, rakamları yaz. Aynı hücreye birden çok rakam yazılabilir: `1`
sonra `2` yazmak o hücreye `1 2` ipucusunu koyar. Geri tuşu son rakamı siler,
Delete hücreyi boşaltır. Izgara boyutu yandan değiştirilir.

**Kaydet**, bulmacayı önce çözücüden geçirir ve yalnızca tek çözümlüyse
`dataset/human/puzzles.jsonl` dosyasına ekler. Tek bir rakam yanlış
girildiyse bulmaca neredeyse her zaman çözümsüz ya da çok çözümlü çıkar;
denetim bunu yakalar ve kayıt yapılmaz. Kayıttan sonra ızgara temizlenir ve
kaynak numarası kendiliğinden bir artar, böylece sıradaki bulmacaya geçmek
tek tuş meselesi olur.

Aynı bulmaca iki kez kaydedilmez.

### Çözümden

Çözüm sayfasına bakıyorsan rakamları okumak gereksiz: duvar görünüyorsa her
ipucu hücresinin değeri hesaplanabilir. Sol tık duvar örer (sürükleyerek de
olur), sağ tık ipucu hücresini işaretler. Klavyede boşluk duvar, `O` ipucu
hücresi. Doğrulamadan sonra hesaplanan sayılar ızgarada görünür.

Üç kontrol birden yapılır: çizilen duvar Tapa kurallarına uyuyor mu, türetilen
bulmaca tek çözümlü mü, ve bulunan çözüm çizilen duvarla aynı mı.

**Bu kipte denetim daha zayıftır ve bunu bilmek gerekir.** İpucu değerleri
çizilen duvardan türetildiği için, yanlış çizilmiş ama yine de geçerli bir
duvar tutarlı bir bulmaca üretir ve denetimden geçer. Sayılardan girişte bu
olmaz, çünkü orada sayılar dışarıdan gelir ve çözücü tutarlılığı sınar. Bu
yüzden hesaplanan sayılar ızgarada gösteriliyor: kitaptakiyle göz
karşılaştırması son kontrol.

| Uç nokta | İş |
|---|---|
| `POST /api/human/verify` | sayılardan girileni denetler |
| `POST /api/human/save` | doğrulayıp insan veri kümesine ekler |
| `POST /api/human/verify-solution` | çizilen duvarı denetler, sayıları türetir |
| `POST /api/human/save-solution` | türetip doğrulayıp kaydeder |
| `GET /api/human` | kaydedilenleri listeler |

Metin dosyasından toplu aktarım için `tools/import_human.py` (kısa kod) ve
`tools/from_solution.py` (çözüm ızgarası) duruyor.
