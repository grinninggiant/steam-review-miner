# Steam Review Miner

Herkese açık Steam yorumlarından talep cümleleri çıkarıp anahtar kelime/ikili sözcük ile kümelenmiş Markdown rapor üreten bağımlılıksız Python 3.11+ CLI.

## Kullanım

```sh
./steam-review-miner 413150 --lang english --limit 550 --out report.md
# İsterseniz depo dizinini PATH'e ekleyip steam-review-miner komutunu doğrudan çağırın.
```

`appid` pozitif Steam oyun numarasıdır. Varsayılanlar: `--lang english`, `--limit 500` (tekil yorum hedefi), `--out report.md`. Türkçe yorumlar için `--lang turkish`. Çıktı dosyası çalışma dizinine göre çözülür; `report.md` ve `*.report.md` git tarafından yok sayılır. Başka bir çıktı adı seçerseniz onu commit etmeyin.

`--format json` aynı küme verisini Markdown yerine JSON olarak yazar (varsayılan `--format markdown`, varsayılan çıktı adı bu durumda `report.json`): `appid`, `fetched` (çekilen), `unique` (tekil) ve her küme için `title`, `count` (örnek sayısı) ile en fazla üç kısa (≤140 karakter) alıntı içeren `quotes` alanları bulunan `clusters` listesi. Ham yorumlar JSON'a da yazılmaz; `report.json` ve `*.report.json` git tarafından yok sayılır.

Program herkese açık, anahtarsız `IUserReviewsService/GetAppReviews` Web API uç noktasından (Steam eski `store.steampowered.com/appreviews` uç noktasını kullanımdan kaldırdı) 100'lük sayfaları cursor ile çeker; sayfalar arasında bir saniye bekler, tekrarlayan cursor/boş sayfada durur ve `recommendationid` ile tekilleştirir. `Çekilen yorum` ham sayfa giriş sayısıdır (tekrarları içerir), `Tekil yorum` tekilleştirilmiş sayıdır. Steam az sayfa sunarsa hedefe erişmeyebilir. Her talep kümesinde örnek sayısı ve en fazla üç kısa alıntı vardır; ham yorumlar kaydedilmez. Kümeleme sözcük/ikili sözcük temellidir, anlamca benzer farklı ifadeleri her zaman birleştirmez. Ağ hataları, HTTP hata durumları (ör. hız sınırında 429) ve beklenmeyen yanıtlar işlemi hata ile bitirir.

## Test

```sh
python -m unittest
```

Testler sentetik `tests/fixtures/pages.json` yanıtlarını kullanır, ağa çıkmaz. Python dışında paket gerekmez. MIT lisansı `LICENSE` dosyasındadır.
