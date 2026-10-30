"""Create a sanitized new-user distribution without copying local Quartz data."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_publish import audit_package, env_secrets

README = """QUARTZ — YENİ BİLGİSAYAR KURULUMU
Windows 10/11 x64 ve internet bağlantısı gerekir.

1. Quartz.exe'yi açın. WebView2 eksikse Microsoft kurulumunu onaylayın.
2. İlk kurulumda Codex veya Gemini seçin ve Hesabımla bağlan'a basın.
   Gerekli CLI otomatik indirilir; Desktop/IDE veya önceden Node gerekmez.
3. Resmî giriş ekranında kendi hesabınızla giriş yapın. Parolanızı Quartz'a yazmayın.
4. Bağlı durumu göründüğünde Sohbete geç'i seçin. Tek ajanla da çalışabilirsiniz.

Google hesabı Antigravity CLI kullanır. İsteğe bağlı API anahtarı yolu ayrı API
ücret/kotasına tabidir; sessizce ücretli API'ye geçilmez. Hesap erişimi ve kota
sağlayıcıya bağlıdır. Bu paket kişisel geçmiş, anahtar veya oturum içermez.
Bu sürümün temiz Windows'taki yeni hesap girişi ayrıca kabul testi gerektirir.
"""


def prepare(source, output):
    source, output = Path(source).resolve(strict=True), Path(output).resolve()
    if output == source or source in output.parents or output in source.parents:
        raise ValueError('Kaynak ve dağıtım klasörleri ayrı olmalı')
    if output.exists():
        raise FileExistsError('Dağıtım hedefi mevcut; üzerine yazılmaz')
    # Refuse contaminated input; do not silently pretend a developer dist is clean.
    audit = audit_package(source, env_secrets())
    if audit['status'] != 'PASS':
        raise ValueError('Kaynak paket temiz değil; yeni PyInstaller staging paketi kullanın')
    output.mkdir(parents=True)
    shutil.copy2(source / 'Quartz.exe', output / 'Quartz.exe')
    shutil.copytree(source / '_internal', output / '_internal', symlinks=False)
    (output / 'README.txt').write_text(README, encoding='utf-8')
    hashes = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in output.rglob('*') if p.is_file()}
    manifest = {'schema': 1, 'purpose': 'clean-new-user-distribution', 'files': hashes,
                'personal_data_included': False, 'clean_windows_auth_acceptance': 'NOT TESTED'}
    (output / 'release-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    final = audit_package(output, env_secrets())
    if final['status'] != 'PASS':
        raise RuntimeError('Son dağıtım denetimi başarısız')
    return final


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output), indent=2))
