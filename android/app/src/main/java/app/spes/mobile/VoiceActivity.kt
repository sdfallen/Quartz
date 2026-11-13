package app.spes.mobile

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Locale
import kotlin.concurrent.thread

/**
 * Walkie-talkie voice mode: SpeS speaks, then listens. "Dur", "durum" and "tekrar dene"
 * are handled on the phone at once; anything else goes to the team (read-only, like every
 * phone message) and the replies are read aloud as they arrive. Speech recognition and
 * speech output are Android's own (no third-party service added by SpeS).
 */
class VoiceActivity : ComponentActivity(), TextToSpeech.OnInitListener {
    private enum class Phase(val label: String) { Speaking("SpeS konuşuyor"), Listening("Dinliyorum"), Waiting("Ekip düşünüyor"), Idle("Mikrofona dokun") }

    private val phase = mutableStateOf(Phase.Idle)
    private val heard = mutableStateOf("")
    private val said = mutableStateOf("")
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var recognizer: SpeechRecognizer? = null
    private var pendingSpeech: String? = null
    @Volatile private var open = true
    @Volatile private var waitingSeq = -1
    // Conversation loop (live 13 Nov: it answered once and stopped listening).
    @Volatile private var listenWhenQuiet = false
    private var silentTries = 0

    private val micPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) listen() else say("Mikrofon izni olmadan seni duyamam. Yazarak da konuşabilirsin.", listenAfter = false)
    }
    private val fallbackRecognizer = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val text = result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull().orEmpty()
        if (text.isNotBlank()) handle(text) else phase.value = Phase.Idle
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Notifier.cancelAlarm(this)
        tts = TextToSpeech(this, this)
        pendingSpeech = intent.getStringExtra(EXTRA_OPENING) ?: "Merhaba, SpeS seni dinliyor. Ne sormak istersin?"
        setContent { SpesTheme { Screen() } }
    }

    override fun onInit(status: Int) {
        val engine = tts ?: return
        if (status == TextToSpeech.SUCCESS) {
            engine.language = Locale("tr", "TR")
            engine.setSpeechRate(1.05f)
            engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(id: String?) {}
                override fun onError(id: String?) { runOnUiThread { afterSpeech(id) } }
                override fun onDone(id: String?) { runOnUiThread { afterSpeech(id) } }
            })
            ttsReady = true
        }
        pendingSpeech?.let { pendingSpeech = null; say(it) }
    }

    private fun afterSpeech(id: String?) {
        if (!open) return
        val stillTalking = tts?.isSpeaking == true
        if (id == UTTER_LISTEN || (listenWhenQuiet && !stillTalking)) {
            listenWhenQuiet = false
            listen()
        } else if (phase.value == Phase.Speaking && !stillTalking) {
            phase.value = if (waitingSeq >= 0) Phase.Waiting else Phase.Idle
        }
    }

    /** Back to listening once the last queued sentence has been read. */
    private fun listenWhenDone() {
        if (tts?.isSpeaking == true) listenWhenQuiet = true else listen()
    }

    private fun say(text: String, listenAfter: Boolean = true, queue: Boolean = false) {
        said.value = text
        val engine = tts
        if (!ttsReady || engine == null) { phase.value = Phase.Idle; return }
        phase.value = Phase.Speaking
        // Team replies queue up behind each other; a new answer never cuts the previous one off.
        engine.speak(text, if (queue) TextToSpeech.QUEUE_ADD else TextToSpeech.QUEUE_FLUSH, null,
            if (listenAfter) UTTER_LISTEN else UTTER_ONLY)
    }

    private fun listen() {
        if (!open) return
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            micPermission.launch(Manifest.permission.RECORD_AUDIO); return
        }
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "tr-TR")
            .putExtra(RecognizerIntent.EXTRA_PROMPT, "SpeS dinliyor")
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            // Some phones only offer the system dialog.
            runCatching { fallbackRecognizer.launch(intent) }.onFailure { say("Bu telefonda ses tanıma bulunamadı.", listenAfter = false) }
            return
        }
        recognizer?.destroy()
        recognizer = SpeechRecognizer.createSpeechRecognizer(this).apply {
            setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) { phase.value = Phase.Listening; heard.value = "" }
                override fun onBeginningOfSpeech() {}
                override fun onRmsChanged(rmsdB: Float) {}
                override fun onBufferReceived(buffer: ByteArray?) {}
                override fun onEndOfSpeech() {}
                override fun onError(error: Int) {
                    phase.value = if (waitingSeq >= 0) Phase.Waiting else Phase.Idle
                    if (error == SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS) { micPermission.launch(Manifest.permission.RECORD_AUDIO); return }
                    // Silence: listen twice more, then wait for the Konuş button.
                    if ((error == SpeechRecognizer.ERROR_NO_MATCH || error == SpeechRecognizer.ERROR_SPEECH_TIMEOUT)
                        && waitingSeq < 0 && silentTries < 2) {
                        silentTries++
                        window.decorView.postDelayed({ if (open) listen() }, 400)
                    }
                }
                override fun onResults(results: Bundle?) {
                    silentTries = 0
                    val text = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()
                    if (text.isNotBlank()) handle(text) else phase.value = Phase.Idle
                }
                override fun onPartialResults(partial: Bundle?) {
                    partial?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.let { heard.value = it }
                }
                override fun onEvent(eventType: Int, params: Bundle?) {}
            })
            startListening(intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true))
        }
    }

    /** Commands are understood on the phone; everything else is a message to the team. */
    private fun handle(text: String) {
        heard.value = text
        val command = VoiceCommands.parse(text)
        val api = Prefs.api(this)
        when (command) {
            VoiceCommands.Command.Stop -> {
                phase.value = Phase.Waiting
                thread {
                    val ok = runCatching { api.stop() }.isSuccess
                    runOnUiThread { waitingSeq = -1; say(if (ok) "Durdurdum. Başka bir şey var mı?" else "Durduramadım, bilgisayara ulaşamıyorum.") }
                }
            }
            VoiceCommands.Command.Status -> {
                phase.value = Phase.Waiting
                thread {
                    val text2 = runCatching { VoiceCommands.summary(api.state(0, 0)) }.getOrElse { "Bilgisayara ulaşamıyorum. Tailscale açık mı?" }
                    runOnUiThread { say(text2) }
                }
            }
            VoiceCommands.Command.Bye -> { say("Görüşürüz.", listenAfter = false); open = false; window.decorView.postDelayed({ finish() }, 1400) }
            is VoiceCommands.Command.Send -> ask(api, command.text)
        }
    }

    private fun ask(api: SpesApi, text: String) {
        phase.value = Phase.Waiting
        thread {
            val before = runCatching { api.state(0, 0).lastSeq }.getOrDefault(0)
            val sent = runCatching { api.send(text) }
            if (sent.isFailure) { runOnUiThread { say(sent.exceptionOrNull()?.message ?: "Mesaj gönderilemedi.") }; return@thread }
            waitingSeq = before
            // Read replies aloud as they arrive; stop when the team is done (or after 3 minutes).
            val deadline = System.currentTimeMillis() + 180_000
            val spoken = HashSet<String>()
            var after = before
            while (open && System.currentTimeMillis() < deadline) {
                val s = runCatching { api.state(after, 20) }.getOrNull()
                if (s == null) { Thread.sleep(3_000); continue }
                val fresh = s.messages.filter { !it.fromUser && it.text.isNotBlank() && spoken.add(it.id) }
                if (fresh.isNotEmpty()) {
                    val speech = fresh.joinToString(" ") { "${it.persona.ifBlank { "SpeS" }}: ${VoiceCommands.forSpeech(it.text)}" }
                    runOnUiThread { say(speech, listenAfter = false, queue = true) }
                }
                after = maxOf(after, s.lastSeq)
                // The team is done as soon as it is idle and has answered; do not wait for another poll.
                if (!s.busy && s.lastSeq > before) break
            }
            waitingSeq = -1
            runOnUiThread { if (open) listenWhenDone() }
        }
    }

    override fun onDestroy() {
        open = false
        recognizer?.destroy()
        tts?.stop(); tts?.shutdown()
        super.onDestroy()
    }

    @androidx.compose.runtime.Composable
    private fun Screen() {
        val p by phase
        val transition = rememberInfiniteTransition(label = "voice")
        val pulse by transition.animateFloat(1f, if (p == Phase.Listening) 1.18f else if (p == Phase.Speaking) 1.08f else 1f,
            infiniteRepeatable(tween(if (p == Phase.Listening) 600 else 900, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "pulse")
        Column(Modifier.fillMaxSize().background(SpesColors.bg).safeDrawingPadding().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.SpaceBetween) {
            Text(p.label, color = SpesColors.text2, fontSize = 16.sp, modifier = Modifier.padding(top = 12.dp))
            Box(contentAlignment = Alignment.Center) {
                Box(Modifier.size(200.dp).graphicsLayer { scaleX = pulse; scaleY = pulse }.clip(CircleShape)
                    .background(when (p) { Phase.Listening -> SpesColors.accent.copy(alpha = .18f); Phase.Speaking -> SpesColors.fatum.copy(alpha = .16f); else -> SpesColors.surface1 }))
                Image(painterResource(R.drawable.ic_launcher_foreground), contentDescription = null, modifier = Modifier.size(150.dp))
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                if (said.value.isNotBlank()) Text(said.value, color = SpesColors.text, fontSize = 18.sp, textAlign = TextAlign.Center, lineHeight = 26.sp)
                if (heard.value.isNotBlank()) {
                    Spacer(Modifier.height(14.dp))
                    Text("Sen: ${heard.value}", color = SpesColors.text3, fontSize = 15.sp, textAlign = TextAlign.Center)
                }
            }
            Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(onClick = { tts?.stop(); silentTries = 0; listen() }, modifier = Modifier.fillMaxWidth().height(64.dp), shape = CircleShape) {
                    Text(if (p == Phase.Listening) "Dinliyorum…" else "Konuş", fontSize = 18.sp)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Button(onClick = { handle("dur") }, modifier = Modifier.weight(1f).height(52.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = SpesColors.stop, contentColor = SpesColors.text)) { Text("Dur") }
                    OutlinedButton(onClick = { open = false; finish() }, modifier = Modifier.weight(1f).height(52.dp)) { Text("Kapat", color = SpesColors.text2) }
                }
            }
        }
    }

    companion object {
        const val EXTRA_OPENING = "opening"
        private const val UTTER_LISTEN = "listen"
        private const val UTTER_ONLY = "only"
    }
}
