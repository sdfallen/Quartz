package app.spes.mobile

import java.util.Locale

/** Plain-Kotlin voice helpers (no Android types) so they stay easy to read and test. */
object VoiceCommands {
    sealed class Command {
        data object Stop : Command()
        data object Status : Command()
        data object Bye : Command()
        data class Send(val text: String) : Command()
    }

    private val tr = Locale("tr", "TR")

    fun parse(raw: String): Command {
        val t = raw.trim().lowercase(tr).trimEnd('.', '!', '?')
        return when {
            t in setOf("dur", "durdur", "stop", "dur dur", "her şeyi durdur", "işi durdur") || t.startsWith("dur ") && t.length < 14 -> Command.Stop
            t in setOf("durum", "durum ne", "durum nedir", "ne oldu", "neler oluyor", "ne durumdayız", "son durum") -> Command.Status
            t in setOf("görüşürüz", "kapat", "tamam kapat", "hoşça kal", "bitti") -> Command.Bye
            t in setOf("tekrar dene", "yeniden dene", "bir daha dene") ->
                Command.Send("Son hatayı tekrar kontrol eder misiniz? Kısaca ne olduğunu söyleyin.")
            else -> Command.Send(raw.trim())
        }
    }

    /** What the team is doing, in one or two spoken sentences. */
    fun summary(state: SpesApi.State): String {
        val last = state.messages.lastOrNull { !it.fromUser && it.text.isNotBlank() }
        val doing = if (state.busy) state.progress.ifBlank { "Ekip çalışıyor." } else "Ekip şu an boşta."
        return if (last == null) doing else "$doing Son mesaj ${last.persona.ifBlank { "SpeS" }}'tan: ${forSpeech(last.text)}"
    }

    /** Short and speakable: technical details, code and links are not read aloud. */
    fun forSpeech(text: String): String {
        var t = text.substringBefore("---TEKNIK_AYRINTILAR---")
        t = t.replace(Regex("```[\\s\\S]*?```"), " kod bloğu ").replace(Regex("https?://\\S+"), " bağlantı ")
        t = t.replace(Regex("[*_#`>|]"), " ").replace(Regex("\\s+"), " ").trim()
        return if (t.length > 320) t.take(320).substringBeforeLast(' ') + "…" else t
    }
}
