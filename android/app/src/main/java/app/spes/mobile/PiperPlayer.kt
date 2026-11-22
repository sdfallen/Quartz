package app.spes.mobile

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.os.Handler
import android.os.Looper
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.LinkedBlockingDeque
import java.util.concurrent.TimeUnit

/**
 * Reads replies with the desktop's Piper voice (22 Nov). The desktop turns the text into WAV
 * (/api/speech) and this plays it, one sentence group after another. When the desktop has
 * no Piper or cannot be reached, it hands the text back (fallback) and stays off for this
 * voice session, so Android's own voice reads the rest.
 */
class PiperPlayer(
    private val context: Context,
    private val api: SpesApi,
    private val onDone: (String) -> Unit,
    private val fallback: (String, String) -> Unit,
) {
    private data class Item(val text: String, val id: String, val generation: Int)

    private val main = Handler(Looper.getMainLooper())
    private val items = LinkedBlockingDeque<Item>()
    @Volatile private var generation = 0
    @Volatile private var playing: MediaPlayer? = null
    @Volatile private var working = false
    @Volatile private var closed = false
    @Volatile var enabled = true
        private set

    val busy get() = working || items.isNotEmpty()

    private val worker = Thread({ loop() }, "spes-piper").apply { isDaemon = true; start() }

    fun speak(text: String, id: String, queue: Boolean) {
        if (!queue) stop()
        items.put(Item(text, id, generation))
    }

    fun stop() {
        generation++
        items.clear()
        runCatching { playing?.stop() }
    }

    fun close() {
        closed = true
        stop()
        worker.interrupt()
    }

    private fun loop() {
        while (!closed) {
            val item = try { items.take() } catch (_: InterruptedException) { return }
            if (item.generation != generation) continue
            working = true
            try {
                if (!enabled) { handBack(item); continue }
                val audio = runCatching { api.speech(item.text) }.getOrNull()
                if (audio == null) { enabled = false; handBack(item); continue }
                if (item.generation != generation) continue
                play(audio)
                // Not busy any more before the listener asks whether SpeS is still talking.
                working = false
                if (item.generation == generation) main.post { onDone(item.id) }
            } finally {
                working = false
            }
        }
    }

    /** Piper is not available: this item and everything queued go to Android's voice. */
    private fun handBack(item: Item) {
        val rest = ArrayList<Item>().apply { add(item); items.drainTo(this) }
        main.post { rest.filter { it.generation == generation }.forEach { fallback(it.text, it.id) } }
    }

    private fun play(audio: ByteArray) {
        val file = File(context.cacheDir, "spes-voice.wav")
        file.writeBytes(audio)
        val done = CountDownLatch(1)
        val player = MediaPlayer()
        try {
            player.setAudioAttributes(AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANT)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
            player.setDataSource(file.absolutePath)
            player.setOnCompletionListener { done.countDown() }
            player.setOnErrorListener { _, _, _ -> done.countDown(); true }
            player.prepare()
            playing = player
            player.start()
            // A stopped player never completes; poll so Dur ends the wait at once.
            val mine = generation
            while (!done.await(200, TimeUnit.MILLISECONDS)) {
                if (mine != generation || closed) break
            }
        } catch (_: Exception) {
        } finally {
            playing = null
            runCatching { player.release() }
            file.delete()
        }
    }
}
