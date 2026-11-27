package cm.nkapmobile.sdk

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import cm.nkapmobile.sdk.context.ViewTreeScanner
import cm.nkapmobile.sdk.core.*
import cm.nkapmobile.sdk.net.BrainClient
import cm.nkapmobile.sdk.net.HealthInfo
import cm.nkapmobile.sdk.ui.JarvisOrbView
import cm.nkapmobile.sdk.ui.NkapChatDrawer
import cm.nkapmobile.sdk.ui.NkapOverlayView
import cm.nkapmobile.sdk.voice.NkapVoiceController

data class NkapConfig(
    val brainUrl: String = NkapSDK.DEFAULT_BRAIN_URL,
    val langHint: String = "fr",
)

/**
 * Point d'entrée public du SDK Android NkapMobile (.aar) :
 *
 * Intégration en 2 lignes dans n'importe quelle Activity Android :
 * ```kotlin
 * val nkap = NkapSDK.attach(this, NkapConfig(brainUrl = "https://13.51.168.107.sslip.io"))
 * ```
 */
object NkapSDK {
    const val DEFAULT_BRAIN_URL = "https://13.51.168.107.sslip.io"

    fun attach(activity: Activity, config: NkapConfig = NkapConfig()): NkapSession {
        val session = NkapSession(
            context = activity,
            config = config,
            contextProvider = { ViewTreeScanner.scan(activity) },
        )
        session.mountInActivity(activity)
        return session
    }

    fun checkHealth(brainUrl: String = DEFAULT_BRAIN_URL, callback: (HealthInfo) -> Unit) {
        BrainClient(brainUrl).checkHealth(callback)
    }
}

/**
 * Orchestrateur d'une session NkapSDK (utilisable à la fois en mode SDK intégré .aar
 * dans une Activity ET en mode AccessibilityService universel).
 */
class NkapSession(
    private val context: Context,
    config: NkapConfig = NkapConfig(),
    private val contextProvider: () -> ScreenContext,
) {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val rules = CompositionRules()
    private val scheduledRunnables = ArrayList<Runnable>()
    private val d = context.resources.displayMetrics.density
    private fun dp(v: Int): Int = (v * d).toInt()

    val brainClient = BrainClient(config.brainUrl)
    private val langHint = config.langHint

    val overlayView = NkapOverlayView(context)
    lateinit var orbView: JarvisOrbView
        private set
    lateinit var drawerView: NkapChatDrawer
        private set
    val voiceController: NkapVoiceController

    private var rootFrame: FrameLayout? = null
    private var speechRecognizer: SpeechRecognizer? = null
    private var isListening = false
    private var lastContext: ScreenContext? = null

    private var orbMarginLeft = 0
    private var orbMarginTop = 0
    private var mounted = false

    /** Hooks optionnels utilisés quand la session est montée via WindowManager (AccessibilityService). */
    var onOrbDraggedExternal: ((dx: Float, dy: Float) -> Unit)? = null
    var onDrawerToggledExternal: ((visible: Boolean) -> Unit)? = null

    init {
        voiceController = NkapVoiceController(context) { speaking ->
            if (!isListening) {
                orbView.state = if (speaking) JarvisOrbView.OrbState.SPEAKING else JarvisOrbView.OrbState.IDLE
            }
        }
        orbView = JarvisOrbView(
            ctx = context,
            onTap = { toggleDrawer() },
            onDragDelta = { dx, dy ->
                val ext = onOrbDraggedExternal
                if (ext != null) ext(dx, dy) else moveOrbBy(dx, dy)
            },
            onDragEnd = { positionDrawerNearOrb() },
        )
        drawerView = NkapChatDrawer(
            ctx = context,
            onAsk = { q -> ask(q) },
            onClear = { clearAll() },
            onToggleVoice = {
                voiceController.audioEnabled = !voiceController.audioEnabled
                if (!voiceController.audioEnabled) voiceController.stopAll()
                voiceController.audioEnabled
            },
            onToggleMic = { toggleMic() },
            onClose = { closeDrawer() },
        )
    }

    /** Monte l'overlay + l'orbe Jarvis + le tiroir chat directement dans la DecorView d'une Activity. */
    fun mountInActivity(activity: Activity) {
        if (mounted) return
        mounted = true
        val decor = activity.window?.decorView as? ViewGroup ?: return

        val container = FrameLayout(activity).apply {
            tag = ViewTreeScanner.OVERLAY_TAG
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            )
            isClickable = false
            isFocusable = false
        }

        container.addView(
            overlayView,
            FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT)
        )

        val orbSize = dp(74)
        val screenW = activity.resources.displayMetrics.widthPixels
        orbMarginLeft = (screenW - orbSize - dp(12)).coerceAtLeast(dp(8))
        orbMarginTop = dp(52)

        val orbLp = FrameLayout.LayoutParams(orbSize, orbSize + dp(10)).apply {
            gravity = Gravity.TOP or Gravity.START
            leftMargin = orbMarginLeft
            topMargin = orbMarginTop
        }
        container.addView(orbView, orbLp)

        drawerView.visibility = View.GONE
        val drawerW = (screenW - dp(24)).coerceAtMost(dp(344))
        val drawerLp = FrameLayout.LayoutParams(drawerW, FrameLayout.LayoutParams.WRAP_CONTENT).apply {
            gravity = Gravity.TOP or Gravity.START
            leftMargin = (screenW - drawerW) / 2
            topMargin = orbMarginTop + orbSize + dp(8)
        }
        container.addView(drawerView, drawerLp)

        decor.addView(container)
        rootFrame = container
    }

    private fun moveOrbBy(dx: Float, dy: Float) {
        val parent = rootFrame ?: return
        val lp = orbView.layoutParams as? FrameLayout.LayoutParams ?: return
        val maxX = (parent.width - orbView.width - dp(6)).coerceAtLeast(dp(6))
        val maxY = (parent.height - orbView.height - dp(16)).coerceAtLeast(dp(32))
        orbMarginLeft = (orbMarginLeft + dx.toInt()).coerceIn(dp(6), maxX)
        orbMarginTop = (orbMarginTop + dy.toInt()).coerceIn(dp(28), maxY)
        lp.leftMargin = orbMarginLeft
        lp.topMargin = orbMarginTop
        orbView.layoutParams = lp
        if (drawerView.visibility == View.VISIBLE) positionDrawerNearOrb()
    }

    private fun positionDrawerNearOrb() {
        val parent = rootFrame ?: return
        val lp = drawerView.layoutParams as? FrameLayout.LayoutParams ?: return
        val w = lp.width.takeIf { it > 0 } ?: dp(320)
        val left = (orbMarginLeft + orbView.width - w).coerceIn(dp(10), (parent.width - w - dp(10)).coerceAtLeast(dp(10)))
        val spaceBelow = parent.height - (orbMarginTop + orbView.height) - dp(24)
        val top = if (spaceBelow < dp(240) && orbMarginTop > dp(260)) {
            (orbMarginTop - dp(310)).coerceAtLeast(dp(36))
        } else {
            (orbMarginTop + orbView.height + dp(8)).coerceAtMost((parent.height - dp(220)).coerceAtLeast(dp(40)))
        }
        lp.leftMargin = left
        lp.topMargin = top
        drawerView.layoutParams = lp
    }

    fun toggleDrawer() {
        if (drawerView.visibility == View.VISIBLE) {
            closeDrawer()
        } else {
            val ctx = runCatching { contextProvider() }.getOrNull()
            lastContext = ctx
            drawerView.refreshSuggestions(ctx?.screenHint ?: "home", brainClient.brainUrl.isNotBlank())
            positionDrawerNearOrb()
            drawerView.visibility = View.VISIBLE
            drawerView.alpha = 0f
            drawerView.translationY = -12f * d
            drawerView.animate().alpha(1f).translationY(0f).setDuration(200).start()
            orbView.showLabel = true
            onDrawerToggledExternal?.invoke(true)
        }
    }

    fun closeDrawer() {
        drawerView.visibility = View.GONE
        if (!isListening) orbView.showLabel = false
        onDrawerToggledExternal?.invoke(false)
    }

    fun ask(question: String) {
        val q = question.trim()
        if (q.isEmpty()) return
        closeDrawer()
        cancelScheduled()
        voiceController.stopAll()
        overlayView.clearAll()
        rules.onCleared()

        val ctx = runCatching { contextProvider() }.getOrElse {
            ScreenContext(context.packageName, "Application", "home", "mobile", emptyList())
        }
        lastContext = ctx
        orbView.state = JarvisOrbView.OrbState.THINKING
        overlayView.showCaption("Réflexion en cours…")

        brainClient.ask(
            question = q,
            context = ctx,
            langHint = langHint,
            onResult = { actions ->
                mainHandler.post {
                    if (actions.isEmpty()) {
                        orbView.state = JarvisOrbView.OrbState.IDLE
                        overlayView.showCaption("Je n'ai pas reçu d'action exploitable.")
                        return@post
                    }
                    playActions(actions, ctx)
                }
            },
            onError = { err ->
                mainHandler.post {
                    orbView.state = JarvisOrbView.OrbState.IDLE
                    overlayView.showCaption("Serveur indisponible ($err)")
                }
            },
        )
    }

    fun playActions(actions: List<TimedAction>, ctx: ScreenContext) {
        cancelScheduled()
        overlayView.clearAll()
        rules.onCleared()

        var nextDrawAt = 0L
        var hasClear = false

        for (item in actions) {
            val act = item.action
            val isDraw = act is NkapAction.Circle || act is NkapAction.Box || act is NkapAction.Underline ||
                act is NkapAction.Highlight || act is NkapAction.Frame || act is NkapAction.Arrow ||
                act is NkapAction.Callout || act is NkapAction.NumBadge || act is NkapAction.Strike ||
                act is NkapAction.Check || act is NkapAction.Cross

            var delay = item.runAfterMs.toLong().coerceAtLeast(0L)
            if (isDraw) {
                if (delay < nextDrawAt) delay = nextDrawAt
                nextDrawAt = delay + 580L
            } else if (act is NkapAction.Clear) {
                hasClear = true
                if (delay < nextDrawAt + 3200L) delay = nextDrawAt + 3200L
            }

            val r = Runnable { executeAction(act, ctx) }
            scheduledRunnables.add(r)
            if (delay == 0L) r.run() else mainHandler.postDelayed(r, delay)
        }

        if (!hasClear) {
            val clearR = Runnable { scheduleClearAfterVoice() }
            scheduledRunnables.add(clearR)
            mainHandler.postDelayed(clearR, (nextDrawAt + 4200L).coerceAtLeast(6000L))
        }
    }

    private fun executeAction(act: NkapAction, ctx: ScreenContext) {
        when (act) {
            is NkapAction.Speak -> {
                overlayView.showCaption(act.text, act.subFr)
                voiceController.enqueue(act.text, act.audioUrl)
            }
            is NkapAction.Caption -> overlayView.showCaption(act.text, act.subFr)
            is NkapAction.Circle -> {
                val n = ctx.resolve(act.target) ?: return
                enforceBudget(act.id)
                overlayView.showCircle(n, act.color, act.durationMs, act.id)
            }
            is NkapAction.Box -> {
                val n = ctx.resolve(act.target) ?: return
                enforceBudget(act.id)
                overlayView.showBox(n, act.color, act.durationMs, act.id)
            }
            is NkapAction.Underline -> {
                val n = ctx.resolve(act.target) ?: return
                enforceBudget(act.id)
                overlayView.showUnderline(n, act.color, act.durationMs, act.id)
            }
            is NkapAction.Highlight -> {
                val n = ctx.resolve(act.target) ?: return
                enforceBudget(act.id)
                overlayView.showHighlight(n, act.color, act.durationMs, act.id)
            }
            is NkapAction.Frame -> {
                val n = ctx.resolve(act.target) ?: return
                enforceBudget(act.id)
                overlayView.showFrame(n, act.label, act.color, act.pad, act.id)
            }
            is NkapAction.Arrow -> {
                val a = ctx.resolve(act.from)
                val b = ctx.resolve(act.to)
                if (a != null && b != null) {
                    enforceBudget(act.id)
                    overlayView.showArrow(a, b, act.color, act.durationMs, act.bow, act.id)
                }
            }
            is NkapAction.Write -> {
                val n = ctx.resolve(act.target) ?: return
                enforceBudget(act.id)
                overlayView.showWrite(act.text, n, act.size, act.color, act.backing, act.perLetterMs, act.id)
            }
            is NkapAction.Callout -> {
                val n = ctx.resolve(act.target) ?: return
                enforceBudget(act.id)
                overlayView.showCallout(n, act.label, act.color, act.id)
            }
            is NkapAction.NumBadge -> {
                val n = ctx.resolve(act.target) ?: return
                enforceBudget(act.id)
                overlayView.showNum(n, act.step, act.label, act.color, act.id)
            }
            is NkapAction.Strike -> {
                val n = ctx.resolve(act.target) ?: return
                enforceBudget(act.id)
                overlayView.showStrike(n, act.color, act.durationMs, act.id)
            }
            is NkapAction.Check -> {
                val n = ctx.resolve(act.target) ?: return
                enforceBudget(act.id)
                overlayView.showCheck(n, act.color, act.durationMs, act.id)
            }
            is NkapAction.Cross -> {
                val n = ctx.resolve(act.target) ?: return
                enforceBudget(act.id)
                overlayView.showCross(n, act.color, act.durationMs, act.id)
            }
            is NkapAction.Notebook -> {
                val anchor = ctx.resolve(act.anchor)
                overlayView.showNotebook(act, anchor)
            }
            is NkapAction.Hide -> {
                rules.onHidden(act.id)
                overlayView.hideMark(act.id)
            }
            is NkapAction.Clear -> scheduleClearAfterVoice()
        }
    }

    private fun enforceBudget(id: String) {
        rules.onMarkShown(id, max = 3).forEach { overlayView.hideMark(it) }
    }

    private fun scheduleClearAfterVoice() {
        voiceController.onIdleOnce {
            val r = Runnable {
                overlayView.clearAll()
                rules.onCleared()
                if (!voiceController.isSpeaking && !isListening) {
                    orbView.state = JarvisOrbView.OrbState.IDLE
                }
            }
            scheduledRunnables.add(r)
            mainHandler.postDelayed(r, 700L)
        }
    }

    private fun toggleMic() {
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            overlayView.showCaption("Micro vocal non disponible sur cet appareil")
            return
        }
        if (isListening) {
            runCatching { speechRecognizer?.stopListening() }
            isListening = false
            drawerView.setMicActive(false)
            orbView.state = JarvisOrbView.OrbState.IDLE
            return
        }
        voiceController.stopAll()
        if (speechRecognizer == null) {
            speechRecognizer = SpeechRecognizer.createSpeechRecognizer(context).apply {
                setRecognitionListener(object : RecognitionListener {
                    override fun onReadyForSpeech(params: Bundle?) {
                        isListening = true
                        drawerView.setMicActive(true)
                        orbView.state = JarvisOrbView.OrbState.LISTENING
                        orbView.showLabel = true
                        overlayView.showCaption("Je t'écoute…")
                    }
                    override fun onBeginningOfSpeech() {}
                    override fun onRmsChanged(rmsdB: Float) {}
                    override fun onBufferReceived(buffer: ByteArray?) {}
                    override fun onEndOfSpeech() {
                        isListening = false
                        drawerView.setMicActive(false)
                    }
                    override fun onError(error: Int) {
                        isListening = false
                        drawerView.setMicActive(false)
                        orbView.state = JarvisOrbView.OrbState.IDLE
                        overlayView.showCaption(null)
                    }
                    override fun onResults(results: Bundle?) {
                        isListening = false
                        drawerView.setMicActive(false)
                        val text = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()
                        if (!text.isNullOrBlank()) ask(text)
                        else orbView.state = JarvisOrbView.OrbState.IDLE
                    }
                    override fun onPartialResults(partialResults: Bundle?) {}
                    override fun onEvent(eventType: Int, params: Bundle?) {}
                })
            }
        }
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "fr-FR")
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }
        runCatching { speechRecognizer?.startListening(intent) }
    }

    private fun cancelScheduled() {
        scheduledRunnables.forEach { mainHandler.removeCallbacks(it) }
        scheduledRunnables.clear()
    }

    fun clearAll() {
        cancelScheduled()
        voiceController.stopAll()
        overlayView.clearAll()
        rules.onCleared()
        orbView.state = JarvisOrbView.OrbState.IDLE
    }

    fun destroy() {
        cancelScheduled()
        voiceController.shutdown()
        runCatching { speechRecognizer?.destroy() }
        speechRecognizer = null
        rootFrame?.let { (it.parent as? ViewGroup)?.removeView(it) }
        rootFrame = null
        mounted = false
    }
}
