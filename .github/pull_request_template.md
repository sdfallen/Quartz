## Amaç

Değişikliğin çözdüğü somut problemi ve kullanıcıya etkisini açıklayın.

## Doğrulama

- [ ] `python -B scripts/check_python_syntax.py`
- [ ] `python -B scripts/check_gui_javascript.py`
- [ ] `python -B scripts/run_safe_tests.py`
- [ ] `python -B scripts/audit_publish.py --staged --history`

Canlı masaüstü testi yapıldıysa kullanılan build, uygulama ve gerçek kanıt
kapsamını yazın. Yapılmadıysa bunu açıkça belirtin.

## Güvenlik ve veri

- [ ] Kullanıcı verisi, anahtar, oturum, log veya paketli EXE eklenmedi.
- [ ] Yeni izin/yetki kapsamı ve geri alma davranışı açıklandı.
- [ ] Warband/ASTER değişikliği varsa Universal Modder sınırı korundu.
