"""Teszt HTML minták az nCore parser ellenőrzéséhez.

Szándékosan több változat: normál találati lista, egyetlen találat,
"nincs találat", hiányos sorok, ékezetes/HTML-entitásos címek.
"""

SEARCH_RESULTS = """
<html><head>
<link rel="alternate" type="application/rss+xml" href="https://ncore.pro/rss.php?key=abc123def456" title="nCore RSS">
</head><body>
<div class="box_torrent_all">

  <div class="box_torrent">
    <div class="box_alap_img">
      <a href="/torrents.php?tipus=hd_hun"><img src="/pic/categ/hd_hun.gif" class="categ_link" alt="Film/HU" title="Film/HU"></a>
    </div>
    <div class="box_nev2">
      <a href="/torrents.php?action=details&amp;id=1234567" onclick="torrent(1234567); return false;" title="Interstellar.2014.HUNGARIAN.1080p.BluRay.DTS.x264-CiNEFiLE">Interstellar.2014.HUNGARI...</a>
    </div>
    <div class="box_feltoltve2">2019-03-11<br>21:14:07</div>
    <div class="box_meret2">12.42 GiB</div>
    <div class="box_d2"><a class="torrent" href="/torrents.php?action=details&amp;id=1234567">148</a></div>
    <div class="box_s2"><a class="torrent" href="/torrents.php?action=details&amp;id=1234567">42</a></div>
    <div class="box_l2"><a class="torrent" href="/torrents.php?action=details&amp;id=1234567">3</a></div>
  </div>

  <div class="box_torrent">
    <div class="box_alap_img">
      <a href="/torrents.php?tipus=hd"><img src="/pic/categ/hd.gif" class="categ_link" alt="Film/EN" title="Film/EN"></a>
    </div>
    <div class="box_nev2">
      <a href="/torrents.php?action=details&amp;id=7654321" onclick="torrent(7654321); return false;" title="Interstellar.2014.2160p.UHD.BluRay.x265-TERMiNAL">Interstellar.2014.2160p...</a>
    </div>
    <div class="box_feltoltve2">2020-08-02<br>09:00:11</div>
    <div class="box_meret2">48.10 GiB</div>
    <div class="box_d2"><a class="torrent" href="#">12</a></div>
    <div class="box_s2"><a class="torrent" href="#">7</a></div>
    <div class="box_l2"><a class="torrent" href="#">11</a></div>
  </div>

  <div class="box_torrent">
    <div class="box_alap_img">
      <a href="/torrents.php?tipus=hd_hun"><img src="/pic/categ/hd_hun.gif" class="categ_link" alt="Film/HU" title="Film/HU"></a>
    </div>
    <div class="box_nev2">
      <a href="/torrents.php?action=details&amp;id=42" onclick="torrent(42); return false;" title="Sz&eacute;p &#233;s a Sz&ouml;rnyeteg 2017 HUN 720p">Szep es a Szornyeteg...</a>
    </div>
    <div class="box_feltoltve2">2021-01-01<br>00:00:01</div>
    <div class="box_meret2">4.5 GiB</div>
    <div class="box_d2"><a class="torrent" href="#">1</a></div>
    <div class="box_s2"><a class="torrent" href="#">0</a></div>
    <div class="box_l2"><a class="torrent" href="#">0</a></div>
  </div>

</div>
</body></html>
"""

SINGLE_RESULT = """
<html><head>
<link rel="alternate" href="https://ncore.pro/rss.php?key=onlykey1" title="RSS">
</head><body>
<div class="box_torrent">
  <div class="box_alap_img">
    <a href="/torrents.php?tipus=hd_hun"><img src="/pic/c.gif" class="categ_link" alt="Film/HU" title="Film/HU"></a>
  </div>
  <div class="box_nev2">
    <a href="/torrents.php?action=details&amp;id=999" onclick="torrent(999); return false;" title="Egyetlen.Talalat.2022.HUN.1080p">Egyetlen...</a>
  </div>
  <div class="box_feltoltve2">2022-05-05<br>12:00:00</div>
  <div class="box_meret2">1 023.50 MiB</div>
  <div class="box_d2"><a class="torrent" href="#">3</a></div>
  <div class="box_s2"><a class="torrent" href="#">5</a></div>
  <div class="box_l2"><a class="torrent" href="#">2</a></div>
</div>
</body></html>
"""

NO_RESULTS = """
<html><head>
<link rel="alternate" href="https://ncore.pro/rss.php?key=abc123def456" title="RSS">
</head><body>
<div class="lista_mini_error">Nincs találat!</div>
</body></html>
"""

#: Seed/leech link nélkül (az nCore néha sima szöveget ad vissza)
PLAIN_PEERS = """
<html><body>
<div class="box_torrent">
  <div class="box_alap_img">
    <a href="/torrents.php?tipus=hd_hun"><img src="/pic/c.gif" class="categ_link" alt="Film/HU" title="Film/HU"></a>
  </div>
  <div class="box_nev2">
    <a href="#" onclick="torrent(555); return false;" title="Plain.Peers.2020.HUN.1080p">Plain...</a>
  </div>
  <div class="box_meret2">2.00 GiB</div>
  <div class="box_s2">17</div>
  <div class="box_l2">4</div>
</div>
</body></html>
"""

#: Teljesen ismeretlen szerkezet - a parser nem dobhat kivételt, üres listát ad
BROKEN_PAGE = "<html><body><div>Karbantartás alatt</div></body></html>"

TORRENT_DETAILS = """
<html><head>
<link rel="alternate" href="https://ncore.pro/rss.php?key=detailkey99" title="RSS">
</head><body>
<div class="torrent_reszletek_cim">Interstellar.2014.HUNGARIAN.1080p.BluRay.DTS.x264-CiNEFiLE</div>
<div class="torrent_reszletek">
  <div class="dt">Típus:</div>
  <div class="dd"><a title="Film" href="/torrents.php?csoport_listazas=osszes_film">Film</a>
    &raquo; <a title="HD/HU" href="/torrents.php?tipus=hd_hun">HD/HU</a></div>
  <div class="dt">Feltöltve:</div>
  <div class="dd">2019-03-11 21:14:07</div>
  <div class="dt">Méret:</div>
  <div class="dd">12.42 GiB (13 336 691 507 bájt)</div>
  <div class="dt">Seederek:</div>
  <div class="dd"><a onclick="peers(); return false;">42</a></div>
  <div class="dt">Leecherek:</div>
  <div class="dd"><a onclick="peers(); return false;">3</a></div>
</div>
<div class="fl_konyvtar">
  <div class="fl_konyvtar_fajl_nev">Interstellar.2014.HUN.1080p.mkv</div>
  <div class="fl_konyvtar_fajl_meret">12.40 GiB</div>
  <div class="fl_konyvtar_fajl_nev">Interstellar.2014.HUN.1080p.srt</div>
  <div class="fl_konyvtar_fajl_meret">64.20 KiB</div>
  <div class="fl_konyvtar_fajl_nev">info.nfo</div>
  <div class="fl_konyvtar_fajl_meret">2.10 KiB</div>
</div>
</body></html>
"""

#: Fájllista nélküli részletes oldal
DETAILS_NO_FILES = """
<html><body>
<div class="torrent_reszletek_cim">Nincs.Fajllista.2021.HUN.1080p</div>
<div class="dd"><a title="Film" href="/torrents.php?csoport_listazas=osszes_film">Film</a>
  <a title="HD/HU" href="/torrents.php?tipus=hd_hun">HD/HU</a></div>
<div class="dd">7.77 GiB (8 343 000 000 bájt)</div>
<div class="dt">Seederek:</div><div class="dd"><a onclick="x()">9</a></div>
<div class="dt">Leecherek:</div><div class="dd"><a onclick="x()">1</a></div>
</body></html>
"""

DETAILS_MISSING = "<html><body><div>Nincs ilyen torrent.</div></body></html>"

LOGIN_PAGE = """
<html><head><title>nCore</title></head><body>
<form action="login.php" method="post">
<input name="nev"><input name="pass" type="password">
</form>
<div class="hiba">Hibás jelszó vagy felhasználónév!</div>
</body></html>
"""

LOGIN_SUCCESS = """
<html><head><title>nCore - Kezdőlap</title>
<link rel="alternate" href="https://ncore.pro/rss.php?key=loginkey42" title="RSS"></head>
<body>Üdv!</body></html>
"""
