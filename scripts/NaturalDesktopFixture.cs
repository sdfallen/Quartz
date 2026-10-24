using System;
using System.IO;
using System.Windows.Forms;
using System.Drawing;

// Disposable acceptance app: only its own log and callback, no user documents.
// The target swatch is painted pixels, not exposed as answer text through UIA.
class NaturalDesktopFixture {
    [STAThread] static void Main() {
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        Directory.CreateDirectory(dir);
        string log = Path.Combine(dir, "test.log");
        string nonce = Guid.NewGuid().ToString("N").Substring(0, 8);
        bool wantsBlue = new Random().Next(2) == 0;
        var form = new Form { Text="Quartz Test Uygulamasi - Tema Hatasi", Width=800, Height=540 };
        var title = new Label { Text="Tema ayarını referans renk ile eşleştirin", Location=new Point(30,20), Width=720, Height=35 };
        var reference = new Panel { AccessibleName="Referans renk örneği", Location=new Point(40,75), Size=new Size(220,110), BackColor=wantsBlue ? Color.RoyalBlue : Color.Goldenrod };
        var actual = new Panel { AccessibleName="Uygulanan renk örneği", Location=new Point(390,75), Size=new Size(220,110), BackColor=wantsBlue ? Color.Goldenrod : Color.RoyalBlue };
        var left = new Label { Text="Referans", Location=new Point(40,190), Width=220 };
        var right = new Label { Text="Mevcut görünüm", Location=new Point(390,190), Width=220 };
        var result = new Label { Text="Durum: Tema uyumsuz", Location=new Point(40,350), Width=680, Height=45 };
        var blue = new Button { Text="Mavi temayı uygula", Location=new Point(40,255), Size=new Size(220,55) };
        var yellow = new Button { Text="Sarı temayı uygula", Location=new Point(390,255), Size=new Size(220,55) };
        var note = new Label { Text="Yalnız geçici test verisi. Kimlik: " + nonce, Location=new Point(40,420), Width=680, Height=30 };
        int actions = 0;
        Action<bool> apply = selectedBlue => {
            actions++;
            bool good = selectedBlue == wantsBlue;
            actual.BackColor = selectedBlue ? Color.RoyalBlue : Color.Goldenrod;
            result.Text = good ? "Durum: Düzeltildi" : "Durum: Tema uyumsuz";
            File.AppendAllText(log, DateTime.UtcNow.ToString("o")+" theme_applied matches_reference="+good+" action="+actions+" nonce="+nonce+Environment.NewLine);
            File.WriteAllText(Path.Combine(dir,"callback.json"),"{\"matches_reference\":"+(good?"true":"false")+",\"action_count\":"+actions+",\"nonce\":\""+nonce+"\"}");
        };
        blue.Click += (s,e) => apply(true);
        yellow.Click += (s,e) => apply(false);
        foreach(Control c in new Control[]{title,reference,actual,left,right,result,blue,yellow,note})form.Controls.Add(c);
        File.AppendAllText(log, DateTime.UtcNow.ToString("o")+" fixture_ready theme_mismatch=true; compare actual visible reference swatch; nonce="+nonce+Environment.NewLine);
        Application.Run(form);
    }
}
