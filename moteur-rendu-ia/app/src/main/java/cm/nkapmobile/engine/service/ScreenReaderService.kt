package cm.nkapmobile.engine.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.graphics.Rect
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import cm.nkapmobile.sdk.NkapConfig
import cm.nkapmobile.sdk.NkapSDK
import cm.nkapmobile.sdk.NkapSession
import cm.nkapmobile.sdk.context.ViewTreeScanner
import cm.nkapmobile.sdk.core.ScreenContext
import cm.nkapmobile.sdk.core.ScreenNode

/**
 * Mode Universel (AccessibilityService) propulsé par le même module `:nkap-sdk-android` :
 * fonctionne par-dessus N'IMPORTE QUELLE application Android (Wave, Orange Money, MTN MoMo, Chrome)
 * sans modifier le code de l'app cible, avec filtre strict anti-PIN/EditText (règle d'or #3).
 */
class ScreenReaderService : AccessibilityService() {

    private val handler = Handler(Looper.getMainLooper())
    private var wm: WindowManager? = null
    private var session: NkapSession? = null
    private var orbLp: WindowManager.LayoutParams? = null
    private var drawerLp: WindowManager.LayoutParams? = null
    private var lastContext: ScreenContext? = null

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    fun snapshot(): ScreenContext {
        val root = rootInActiveWindow
        if (root == null) {
            return lastContext ?: ScreenContext(packageName, "Écran", "home", "mobile", emptyList())
        }
        val pkg = root.packageName?.toString() ?: "?"
        val nodes = ArrayList<ScreenNode>(40)
        walk(root, "root", 0, nodes)
        root.recycle()

        val ctx = ScreenContext(
            appPackage = pkg,
            title = pkg.substringAfterLast('.'),
            screenHint = ViewTreeScanner.guessScreenHint(nodes),
            channel = "mobile",
            nodes = nodes,
        )
        lastContext = ctx
        return ctx
    }

    private fun walk(node: AccessibilityNodeInfo, path: String, depth: Int, out: ArrayList<ScreenNode>) {
        if (depth > 30 || out.size >= 60) return
        val sensitive = node.isPassword || node.className?.toString()?.contains("EditText") == true
        val text = node.text?.toString()?.trim().orEmpty()
        val desc = node.contentDescription?.toString()?.trim().orEmpty()
        val label = if (text.isNotEmpty()) text else desc

        if (label.isNotEmpty() && !sensitive) {
            val r = Rect()
            node.getBoundsInScreen(r)
            if (r.width() > 16 && r.height() > 10 && !r.isEmpty) {
                out.add(
                    ScreenNode(
                        nodeId = "n_%02d".format(out.size + 1),
                        tag = if (node.isClickable) "button" else "span",
                        text = label.replace(Regex("\\s+"), " ").take(120),
                        bounds = intArrayOf(r.left, r.top, r.right, r.bottom),
                        clickable = node.isClickable,
                        tone = "unknown",
                        path = path,
                    )
                )
            }
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val seg = node.className?.toString()?.substringAfterLast('.') ?: "n"
            walk(child, "$path/$seg[$i]", depth + 1, out)
            child.recycle()
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        serviceInfo = serviceInfo?.apply {
            flags = flags or AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
        }
        wm = getSystemService(WINDOW_SERVICE) as WindowManager

        val brainUrl = getSharedPreferences("nkap_sdk", Context.MODE_PRIVATE)
            .getString("brain_url", NkapSDK.DEFAULT_BRAIN_URL) ?: NkapSDK.DEFAULT_BRAIN_URL

        val s = NkapSession(
            context = this,
            config = NkapConfig(brainUrl = brainUrl),
            contextProvider = { snapshot() },
        )
        session = s

        // 1. Couche dessin (non-tactile)
        val overlayLp = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                or WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT,
        ).apply { gravity = Gravity.TOP or Gravity.START }
        wm?.addView(s.overlayView, overlayLp)

        // 2. Orbe neuronal Jarvis (tactile + glisser-déposer manuel)
        val dm = resources.displayMetrics
        val orbSz = dp(74)
        val oLp = WindowManager.LayoutParams(
            orbSz,
            orbSz + dp(10),
            WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = (dm.widthPixels - orbSz - dp(12)).coerceAtLeast(dp(8))
            y = dp(90)
        }
        orbLp = oLp
        wm?.addView(s.orbView, oLp)

        // 3. Tiroir de chat Jarvis (ajouté masqué, devient focusable à l'ouverture pour le clavier)
        val drawerW = (dm.widthPixels - dp(24)).coerceAtMost(dp(344))
        val dLp = WindowManager.LayoutParams(
            drawerW,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
                or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = (dm.widthPixels - drawerW) / 2
            y = oLp.y + orbSz + dp(8)
        }
        drawerLp = dLp
        s.drawerView.visibility = View.GONE
        wm?.addView(s.drawerView, dLp)

        s.onOrbDraggedExternal = { dx, dy ->
            val maxX = (dm.widthPixels - orbSz - dp(6)).coerceAtLeast(dp(6))
            val maxY = (dm.heightPixels - orbSz - dp(24)).coerceAtLeast(dp(40))
            oLp.x = (oLp.x + dx.toInt()).coerceIn(dp(6), maxX)
            oLp.y = (oLp.y + dy.toInt()).coerceIn(dp(40), maxY)
            runCatching { wm?.updateViewLayout(s.orbView, oLp) }
        }
        s.onDrawerToggledExternal = { visible ->
            dLp.flags = if (visible) {
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
            } else {
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
            }
            dLp.x = (oLp.x + orbSz - drawerW).coerceIn(dp(10), (dm.widthPixels - drawerW - dp(10)).coerceAtLeast(dp(10)))
            dLp.y = if (oLp.y + orbSz + dp(280) > dm.heightPixels) {
                (oLp.y - dp(310)).coerceAtLeast(dp(40))
            } else {
                oLp.y + orbSz + dp(8)
            }
            runCatching { wm?.updateViewLayout(s.drawerView, dLp) }
        }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event?.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            handler.postDelayed({ snapshot() }, 180)
        }
    }

    override fun onInterrupt() {}

    override fun onUnbind(intent: Intent?): Boolean {
        session?.let { s ->
            runCatching { wm?.removeView(s.overlayView) }
            runCatching { wm?.removeView(s.orbView) }
            runCatching { wm?.removeView(s.drawerView) }
            s.destroy()
        }
        session = null
        return super.onUnbind(intent)
    }
}
