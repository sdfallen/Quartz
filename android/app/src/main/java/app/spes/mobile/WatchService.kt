package app.spes.mobile

import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import kotlin.concurrent.thread

/**
 * Keeps one long poll open to the desktop (over Tailscale) and turns team events into
 * notifications. No Google/Firebase service is involved: the phone talks to your PC only.
 */
class WatchService : Service() {
    @Volatile private var running = false
    private var worker: Thread? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!Prefs.paired(this) || !Prefs.watching(this)) {
            stopSelf()
            return START_NOT_STICKY
        }
        Notifier.ensureChannels(this)
        val n = Notifier.service(this, "Ekip dinleniyor")
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(Notifier.ID_SERVICE, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_REMOTE_MESSAGING)
        } else {
            startForeground(Notifier.ID_SERVICE, n)
        }
        if (!running) {
            running = true
            worker = thread(name = "spes-watch") { loop() }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        worker?.interrupt()
        super.onDestroy()
    }

    private fun status(text: String) =
        getSystemService(NotificationManager::class.java).notify(Notifier.ID_SERVICE, Notifier.service(this, text))

    private fun loop() {
        var wasBusy = false
        var failures = 0
        while (running) {
            try {
                val api = Prefs.api(this)
                val conversation = Prefs.conversation(this)
                val after = Prefs.lastSeq(this)
                // First contact, or the desktop switched conversation: catch up silently.
                if (conversation.isEmpty() || after == 0) {
                    val now = api.state(0, 0)
                    Prefs.saveCursor(this, now.conversationId, now.lastSeq)
                    wasBusy = now.busy
                    status(if (now.busy) "Ekip çalışıyor" else "Ekip dinleniyor")
                    continue
                }
                val s = api.state(after, 25)
                failures = 0
                if (s.conversationId != conversation || s.lastSeq < after) {
                    Prefs.saveCursor(this, s.conversationId, s.lastSeq)
                    wasBusy = s.busy
                    continue
                }
                val fresh = s.messages.filter { it.seq > after && !it.fromUser }
                val failed = fresh.lastOrNull { it.failed }
                when {
                    failed != null && Prefs.alarms(this) ->
                        Notifier.alarm(this, "${failed.persona.ifBlank { "SpeS" }}: iş başarısız", failed.text.take(240))
                    fresh.isNotEmpty() -> {
                        val last = fresh.last()
                        Notifier.update(this, last.persona.ifBlank { "SpeS" } + " · " + s.title, last.text.take(400))
                    }
                    wasBusy && !s.busy -> Notifier.update(this, "Ekip işi bitirdi", s.title)
                }
                if (wasBusy != s.busy) status(if (s.busy) "Ekip çalışıyor" else "Ekip dinleniyor")
                wasBusy = s.busy
                Prefs.saveCursor(this, s.conversationId, maxOf(after, s.lastSeq))
            } catch (e: SpesApi.AuthException) {
                status("Eşleştirme geçersiz; uygulamayı açın")
                running = false
                stopSelf()
            } catch (e: InterruptedException) {
                return
            } catch (e: Exception) {
                failures += 1
                status("Bilgisayara ulaşılamıyor (Tailscale açık mı?)")
                try {
                    Thread.sleep((5_000L * failures).coerceAtMost(60_000L))
                } catch (_: InterruptedException) {
                    return
                }
            }
        }
    }

    companion object {
        fun start(c: Context) {
            if (Prefs.paired(c) && Prefs.watching(c)) c.startForegroundService(Intent(c, WatchService::class.java))
        }

        fun stop(c: Context) = c.stopService(Intent(c, WatchService::class.java))
    }
}
