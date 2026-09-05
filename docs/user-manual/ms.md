# Penjadual Radio Azan — Manual Pengguna

*Bahasa: [English](en.md) · [العربية](ar.md) · **Bahasa Melayu** · [اردو](ur.md) · [Français](fr.md)*

> **Nota:** Antara muka aplikasi ini sendiri dalam Bahasa Inggeris. Oleh
> itu, nama setiap butang atau halaman disebut dalam Bahasa Inggeris di
> sebelah terjemahannya, supaya anda mudah mencarinya pada skrin.

## Tentang projek ini

Aplikasi ini dicipta oleh Sherif, kerana Allah — dibina secara percuma
supaya sesiapa sahaja boleh melaungkan azan secara automatik pada
pembesar suara pintar mereka sendiri apabila tiba waktu solat, tanpa
sebarang kerja manual harian. Ia percuma untuk digunakan, percuma untuk
dikongsi, dan percuma untuk diubah suai. Jika ia bermanfaat untuk anda
dan keluarga anda, itulah tujuan sebenar ia dibina.

Manual ini menerangkan cara **menggunakan** aplikasi selepas ia dipasang
dan dijalankan — ia tidak merangkumi cara memasangnya pada pelayan
(server) (rujuk [README](../../README.md) utama untuk itu). Ia mengandaikan
seseorang (anda sendiri, rakan yang mahir teknologi, atau ahli keluarga)
telah menyediakannya dan memberikan anda alamat web seperti
`http://<alamat-pelayan-anda>:8730`.

## Membuka aplikasi buat kali pertama

1. Buka alamat web aplikasi ini dalam mana-mana pelayar (komputer atau
   telefon).
2. Buat kali pertama, ia akan meminta anda **mencipta kata laluan
   admin** (Admin password) (sekurang-kurangnya 8 aksara). Ini satu-satunya
   kata laluan yang melindungi aplikasi ini — pilih kata laluan yang
   anda akan ingat, dan jangan kongsikannya dengan sesiapa yang tidak
   sepatutnya dapat menukar tetapan anda.
3. Selepas itu, setiap kali anda membuka aplikasi ini, ia akan meminta
   kata laluan ini untuk log masuk (Login).

## Papan Pemuka (Dashboard)

Ini ialah halaman yang anda akan lihat selepas log masuk. Ia memaparkan:

- Lima waktu solat hari ini, mengikut sumber waktu solat yang anda
  tetapkan.
- Sama ada radio bagi setiap solat sudah bermula/berhenti pada hari
  ini.
- Senarai ringkas aktiviti terkini (berguna untuk semakan pantas, tanpa
  perlu membuka halaman Log penuh).

## Halaman Tetapan (Settings)

### Radio & masa (Radio & timing)

- **URL Strim (Stream URL)** — alamat strim audio stesen radio. Anda
  biasanya tidak perlu menukarnya kecuali stesen itu menukar alamat
  strimnya.
- **Jenis kandungan strim (Stream content type)** — butiran teknikal
  yang diperlukan oleh sesetengah pembesar suara; biarkan seperti asal
  melainkan diminta sebaliknya.
- **Nama stesen (Station name)** — hanya digunakan untuk Alexa, kerana
  Alexa tidak boleh memainkan alamat web secara terus; sebaliknya
  aplikasi ini "meminta" Alexa memainkan stesen ini mengikut nama
  (seperti berkata "Alexa, play *Warna 94.2FM*").
- **Tempoh lalai (Default duration)** — berapa minit radio akan
  dimainkan sebelum berhenti secara automatik.
- **Mula awal (Start early)** — berapa **saat** sebelum waktu solat
  sebenar radio patut mula dimainkan (0 = mula tepat pada waktunya).
  Permulaan awal yang singkat (contohnya 15 saat) boleh berguna supaya
  bunyi sudah bermain sebaik sahaja waktu solat tiba.
- **Zon waktu (Timezone)** — zon waktu yang digunakan untuk
  mengira/memaparkan waktu solat.
- **Sumber waktu solat (Prayer time source)** — pilih **Singapore
  (MUIS)** jika anda berada di Singapura, untuk mendapatkan jadual rasmi
  yang diterbitkan kerajaan. Jika tidak, pilih **Generic (Aladhan)** dan
  masukkan latitud/longitud serta kaedah pengiraan — ini berfungsi di
  mana-mana sahaja di dunia.

Klik **Save** selepas membuat sebarang perubahan. Butang **Refresh
today's prayer times now** akan mengambil semula jadual hari ini secara
manual (secara automatiknya ini berlaku setiap hari).

### Solat (Prayers)

Satu jadual yang membolehkan anda menyesuaikan setiap satu daripada
lima waktu solat secara berasingan:

- **Diaktifkan (Enabled)** — nyahtanda untuk melangkau satu solat
  tertentu sepenuhnya (contohnya jika anda tidak mahu azan automatik
  untuk solat Subuh).
- **Ganti tempoh (Duration override)** — tempoh main yang berbeza
  khusus untuk solat ini, mengatasi tetapan lalai global di atas. Biarkan
  kosong untuk menggunakan tetapan lalai.
- **Ganti mula awal (Start early override)** — masa mula awal yang
  berbeza (dalam saat) khusus untuk solat ini. Biarkan kosong untuk
  menggunakan tetapan lalai global; masukkan `0` supaya solat ini sahaja
  bermula tepat pada waktunya walaupun solat lain bermula awal.

### Kata laluan admin (Admin password)

Tukar kata laluan log masuk anda di sini. Anda perlu memasukkan kata
laluan semasa terlebih dahulu.

## Halaman Peranti (Devices)

Di sinilah anda menyambungkan pembesar suara pintar sebenar anda.

### Peranti yang ditetapkan (jadual di bahagian atas)

Selepas anda menambah sekurang-kurangnya satu peranti, ia akan
dipaparkan di sini bersama:

- **Diaktifkan / Nyahaktifkan (Enabled / Disable)** — hidupkan atau
  matikan sesuatu peranti sepenuhnya tanpa membuangnya.
- **Bermain untuk (Plays for)** — kotak semak untuk setiap satu daripada
  lima solat. Nyahtanda satu solat untuk menghalang **peranti tertentu
  ini** daripada bermain pada waktu solat itu, sambil terus bermain pada
  waktu solat yang lain. Ini membolehkan anda, misalnya, menjadikan
  pembesar suara di bilik tidur hanya bermain untuk Subuh dan Isyak,
  manakala pembesar suara di ruang tamu bermain untuk kelima-lima solat.
- **Ujian (Mula/Henti) — Test (Start/Stop)** — cetuskan peranti secara
  manual sekarang, berguna untuk mengesahkan ia benar-benar berfungsi
  sebelum mempercayakannya pada waktu solat sebenar.
- **Buang (Remove)** — padam peranti ini secara kekal daripada aplikasi
  (anda sentiasa boleh menambahnya semula kemudian melalui carian/
  Discover).

### Menambah pembesar suara Google Home / Nest

1. Klik **Discover Google speakers** — ini mengimbas rangkaian tempatan
   anda selama beberapa saat.
2. Klik **Add** di sebelah pembesar suara yang anda mahu. Ia mesti telah
   disediakan dalam aplikasi Google Home pada telefon anda terlebih
   dahulu.

### Menambah Apple HomePod

1. Klik **Discover HomePods**.
2. Klik **Pair** di sebelah peranti yang anda mahu — HomePod anda akan
   memaparkan (atau mengumumkan) kod PIN.
3. Masukkan PIN tersebut dan sahkan.
4. Klik **Add**.

### Menambah peranti Amazon Alexa / Echo

Alexa tidak menawarkan cara untuk dikawal secara terus seperti Google
dan Apple, jadi aplikasi ini berkomunikasi dengannya melalui **Home
Assistant** (satu program automasi rumah yang berasingan, percuma dan
sumber terbuka) yang telah dipasang dengan tambahan komuniti **Alexa
Media Player** dan telah log masuk ke akaun Amazon anda.

1. Jika Home Assistant dengan Alexa Media Player belum disediakan, minta
   sesiapa yang menguruskan rangkaian anda menyediakannya dahulu
   (langkah teknikal ini hanya dilakukan sekali sahaja).
2. Dalam Home Assistant, jana satu **Token Akses Jangka Panjang
   (Long-Lived Access Token)** (terdapat di bawah profil anda → Security).
3. Kembali ke halaman Peranti (Devices) aplikasi ini, tampalkan alamat
   web Home Assistant anda dan token tersebut ke dalam kad Alexa,
   kemudian klik **Save & test connection**.
4. Klik **Discover Alexa devices** — ini bertanya kepada Home Assistant
   peranti Echo apa yang diketahuinya.
5. Klik **Add** di sebelah setiap pembesar suara sebenar yang anda mahu
   (abaikan mana-mana entri yang kelihatan seperti kumpulan peranti dan
   bukan pembesar suara fizikal sebenar, seperti "Everywhere" atau "Echo
   group").

## Halaman Log (Logs)

Senarai berterusan bagi semua yang telah dilakukan oleh aplikasi ini —
sambungan peranti, permainan dan penghentian yang berjaya/gagal, amaran,
dan ralat. Jika sesuatu solat tidak dimainkan, atau sesuatu peranti
tidak berhenti sepatutnya, ini ialah tempat pertama yang perlu disemak:
ia akan menunjukkan dengan tepat apa yang berlaku dan sebabnya.

## Mendapatkan bantuan

Projek ini adalah sumber terbuka dan percuma untuk sesiapa sahaja
menggunakan, mengubah suai, dan berkongsinya. Jika anda menghadapi
masalah, mempunyai pembetulan terjemahan untuk manual ini, atau ingin
mencadangkan penambahbaikan, sila buka "issue" atau "pull request" di
halaman GitHub projek ini.

*Semoga ia bermanfaat untuk anda dan keluarga anda. Jazakumullahu
khairan.*
