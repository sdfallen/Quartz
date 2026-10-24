using System;
using System.Drawing;
using System.IO;
using System.Threading;
using System.Windows.Forms;

// Disposable three-window test. It only writes inside QUARTZ_FIXTURE_DIR.
class WorkflowFixture {
    static string dir, name, nonce;
    static string State(string key) { return Path.Combine(dir, key + ".txt"); }
    static void Log(string kind) {
        string line = DateTime.UtcNow.ToString("o") + " window=" + name + " event=" + kind + " nonce=" + nonce + Environment.NewLine;
        for (int attempt=0; attempt<20; attempt++) {
            try { File.AppendAllText(Path.Combine(dir,"events.log"),line); return; }
            catch (IOException) { Thread.Sleep(15); }
        }
    }
    [STAThread] static void Main() {
        dir=Environment.GetEnvironmentVariable("QUARTZ_FIXTURE_DIR");
        name=Environment.GetEnvironmentVariable("QUARTZ_FIXTURE_NAME") ?? "C";
        if (String.IsNullOrEmpty(dir) || !Directory.Exists(dir)) return;
        nonce=Environment.GetEnvironmentVariable("QUARTZ_FIXTURE_NONCE") ?? "invalid";
        var form=new Form {Text="Quartz Workflow Fixture " + name, Width=750, Height=490};
        form.Controls.Add(new Label {Text="Quartz guvenli coklu pencere testi - " + name, Location=new Point(30,20), Width=650,Height=40,Font=new Font("Segoe UI",14)});
        if (name=="A") {
            // Color is painted pixels; neither UIA nor the approved log reveals it.
            string color=Environment.GetEnvironmentVariable("QUARTZ_FIXTURE_COLOR") ?? "BLUE";
            File.WriteAllText(State("challenge"),nonce+":"+color);
            form.Controls.Add(new Label {Text="Bu referans rengini B penceresinde secin:",Location=new Point(35,75),Width=600,Height=30});
            form.Controls.Add(new Panel {AccessibleName="Referans renk ornegi",BackColor=color=="BLUE" ? Color.RoyalBlue : Color.Goldenrod,
                Location=new Point(35,115),Width=300,Height=145});
            var status=new Label {Text="Durum: Onarim bekleniyor",Location=new Point(35,290),Width=650,Height=35};
            var finish=new Button {Text="Son kontrolu tamamla",Location=new Point(360,155),Width=270,Height=65};
            int finishCount=0;
            finish.Click+=(s,e)=>{
                finishCount++;
                bool ready=File.Exists(State("repair")) && File.ReadAllText(State("repair")).Trim()==nonce+":"+color;
                if (ready) {
                    status.Text="Durum: Dogrulandi"; Log("finalized");
                    File.WriteAllText(Path.Combine(dir,"final.json"),"{\"verified\":true,\"finish_count\":"+finishCount+",\"nonce\":\""+nonce+"\"}");
                } else { status.Text="Durum: Onarim eksik"; Log("premature_finalize"); }
            };
            var timer=new System.Windows.Forms.Timer {Interval=400};
            timer.Tick+=(s,e)=>{
                if (status.Text=="Durum: Onarim bekleniyor" && File.Exists(State("repair")) && File.ReadAllText(State("repair")).Trim()==nonce+":"+color)
                    status.Text="Durum: Onarim hazir";
            };
            timer.Start(); form.Controls.Add(status);form.Controls.Add(finish);
        } else if (name=="B") {
            form.Controls.Add(new Label {Text="A penceresinde gordugunuz rengi secin.",Location=new Point(35,75),Width=600,Height=30});
            var status=new Label {Text="Durum: Secim bekleniyor",Location=new Point(35,290),Width=650,Height=35};
            int choices=0;
            Action<string> choose=color=>{
                choices++;
                bool correct=File.Exists(State("challenge")) && File.ReadAllText(State("challenge")).Trim()==nonce+":"+color;
                status.Text=correct ? "Durum: Onarim uygulandi" : "Durum: Yanlis secim";
                Log(correct ? "correct_choice" : "wrong_choice");
                File.WriteAllText(Path.Combine(dir,"choice.json"),"{\"correct\":"+(correct?"true":"false")+",\"choice_count\":"+choices+",\"nonce\":\""+nonce+"\"}");
                if(correct)File.WriteAllText(State("repair"),nonce+":"+color);
            };
            var blue=new Button {Text="Mavi onarimi uygula",Location=new Point(35,150),Width=280,Height=80};
            var yellow=new Button {Text="Sari onarimi uygula",Location=new Point(350,150),Width=280,Height=80};
            blue.Click+=(s,e)=>choose("BLUE"); yellow.Click+=(s,e)=>choose("YELLOW");
            form.Controls.Add(blue);form.Controls.Add(yellow);form.Controls.Add(status);
        } else {
            // Never approved: even a matching title must not adopt this window.
            var decoy=new Button {Text="Kapsam disi - dokunma",Location=new Point(160,140),Width=350,Height=90};
            decoy.Click+=(s,e)=>{Log("DECOY_CLICKED");File.WriteAllText(Path.Combine(dir,"decoy.json"),"{\"clicked\":true}");};
            form.Controls.Add(decoy);
        }
        Log("ready");Application.Run(form);
    }
}
