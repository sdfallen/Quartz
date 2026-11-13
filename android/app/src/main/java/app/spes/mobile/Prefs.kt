package app.spes.mobile

import android.content.Context

/** App-private settings. The device key never leaves this file (backups are off). */
object Prefs {
    private fun sp(c: Context) = c.getSharedPreferences("spes", Context.MODE_PRIVATE)

    fun url(c: Context): String = sp(c).getString("url", "") ?: ""
    fun token(c: Context): String = sp(c).getString("token", "") ?: ""
    fun paired(c: Context) = url(c).isNotBlank() && token(c).isNotBlank()

    fun savePairing(c: Context, url: String, token: String) =
        sp(c).edit().putString("url", url).putString("token", token).putInt("last_seq", 0)
            .putString("conversation", "").apply()

    fun forget(c: Context) = sp(c).edit().clear().apply()

    fun watching(c: Context) = sp(c).getBoolean("watching", true)
    fun setWatching(c: Context, on: Boolean) = sp(c).edit().putBoolean("watching", on).apply()

    fun alarms(c: Context) = sp(c).getBoolean("alarms", true)
    fun setAlarms(c: Context, on: Boolean) = sp(c).edit().putBoolean("alarms", on).apply()

    fun lastSeq(c: Context) = sp(c).getInt("last_seq", 0)
    fun conversation(c: Context) = sp(c).getString("conversation", "") ?: ""
    fun saveCursor(c: Context, conversation: String, seq: Int) =
        sp(c).edit().putString("conversation", conversation).putInt("last_seq", seq).apply()

    fun api(c: Context) = SpesApi(url(c), token(c))
}
