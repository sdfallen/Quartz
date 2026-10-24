using System;
using System.IO;
using System.Threading;
using System.Windows.Forms;
using System.Drawing;

// Owned, isolated acceptance fixture. No network, documents or settings.
class MultiWindowFixture {
    [STAThread] static void Main() {
        string dir=Environment.GetEnvironmentVariable("QUARTZ_FIXTURE_DIR");
        string name=Environment.GetEnvironmentVariable("QUARTZ_FIXTURE_NAME") ?? "LAUNCH";
        if (String.IsNullOrEmpty(dir)) {
            // Direct, single-window diagnostic launch; normal A/B/C harness
            // still supplies its own isolated output directory.
            dir=Path.Combine(Path.GetTempPath(),"QuartzPixelFixture");
            Directory.CreateDirectory(dir);
        }
        if (!Directory.Exists(dir)) return;
        var form=new Form {Text="Quartz Multiwindow Fixture " + name, Width=700, Height=420};
        var result=new Label {Text="Clicks: 0",Location=new Point(40,240),Width=600,Height=40};
        var button=new Button {Text="TEST BUTTON "+name,Location=new Point(200,100),Width=250,Height=85};
        int count=0;
        Action<string> log = kind => {
            string line="{\"event\":\""+kind+"\",\"window\":\""+name+"\",\"click_count\":"+count+"}\n";
            // Three independent UI processes write this observer log. A brief
            // sharing violation must not crash a fixture or open a modal.
            for (int attempt=0; attempt<20; attempt++) {
                try { File.AppendAllText(Path.Combine(dir,"events.jsonl"),line); return; }
                catch (IOException) { Thread.Sleep(15); }
            }
            // Keep the UI alive; a missing observer line is a test failure,
            // not a reason to obscure the approved window with an error box.
            File.WriteAllText(Path.Combine(dir,"log-error-"+name+".txt"),kind);
        };
        button.Click+=(s,e)=>{count++;result.Text="Clicks: "+count;log("button_callback");
            File.WriteAllText(Path.Combine(dir,"callback-"+name+".json"),"{\"click_count\":"+count+"}");};
        form.Controls.Add(button);form.Controls.Add(result);
        var timer=new System.Windows.Forms.Timer {Interval=1000};
        timer.Tick+=(s,e)=>log("heartbeat");timer.Start();
        log("fixture_ready");Application.Run(form);
    }
}
