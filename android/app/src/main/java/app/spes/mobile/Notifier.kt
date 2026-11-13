package app.spes.mobile

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build

/** Three channels: the quiet "listening" line, normal updates and the call-like alarm. */
object Notifier {
    const val CH_STATUS = "spes_status"
    const val CH_UPDATES = "spes_updates"
    const val CH_ALARM = "spes_alarm_v1"
    const val ID_SERVICE = 1
    private const val ID_UPDATE = 2
    private const val ID_ALARM = 3

    fun ensureChannels(c: Context) {
        val nm = c.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CH_STATUS, "Bağlantı", NotificationManager.IMPORTANCE_MIN).apply {
            description = "SpeS bilgisayarı dinlerken görünen sessiz satır"
        })
        nm.createNotificationChannel(NotificationChannel(CH_UPDATES, "Ekip mesajları", NotificationManager.IMPORTANCE_DEFAULT).apply {
            description = "Fatum, Fides ve Eos'tan yeni mesajlar; iş bitti bildirimi"
        })
        nm.createNotificationChannel(NotificationChannel(CH_ALARM, "Acil uyarı (arama)", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "Bir iş başarısız olduğunda gelen arama gibi tam ekran uyarı"
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 600, 400, 600, 400, 600)
            setSound(
                RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE),
                AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build(),
            )
        })
    }

    private fun openApp(c: Context) = PendingIntent.getActivity(
        c, 0, Intent(c, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    fun service(c: Context, text: String): Notification =
        Notification.Builder(c, CH_STATUS)
            .setSmallIcon(R.drawable.ic_stat_spes)
            .setContentTitle("SpeS")
            .setContentText(text)
            .setOngoing(true)
            .setContentIntent(openApp(c))
            .build()

    fun update(c: Context, title: String, text: String) {
        val n = Notification.Builder(c, CH_UPDATES)
            .setSmallIcon(R.drawable.ic_stat_spes)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(Notification.BigTextStyle().bigText(text))
            .setAutoCancel(true)
            .setContentIntent(openApp(c))
            .build()
        c.getSystemService(NotificationManager::class.java).notify(ID_UPDATE, n)
    }

    /** The "call": a high-priority notification whose full-screen intent opens AlertActivity. */
    fun alarm(c: Context, title: String, text: String) {
        val intent = Intent(c, AlertActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            .putExtra(AlertActivity.EXTRA_TITLE, title)
            .putExtra(AlertActivity.EXTRA_TEXT, text)
        val pending = PendingIntent.getActivity(c, 1, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n = Notification.Builder(c, CH_ALARM)
            .setSmallIcon(R.drawable.ic_stat_spes)
            .setContentTitle(title)
            .setContentText(text)
            .setCategory(Notification.CATEGORY_CALL)
            .setFullScreenIntent(pending, true)
            .setContentIntent(pending)
            .setAutoCancel(true)
            .build()
        c.getSystemService(NotificationManager::class.java).notify(ID_ALARM, n)
    }

    fun cancelAlarm(c: Context) = c.getSystemService(NotificationManager::class.java).cancel(ID_ALARM)

    /** Android 14+ asks the user to allow full-screen alerts for side-loaded apps. */
    fun canShowFullScreen(c: Context): Boolean =
        Build.VERSION.SDK_INT < 34 || c.getSystemService(NotificationManager::class.java).canUseFullScreenIntent()
}
