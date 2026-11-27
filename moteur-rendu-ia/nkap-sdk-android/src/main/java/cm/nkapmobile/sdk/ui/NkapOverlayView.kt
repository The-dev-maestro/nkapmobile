package cm.nkapmobile.sdk.ui

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.os.SystemClock
import android.view.View
import cm.nkapmobile.sdk.core.*

/**
 * Surface de dessin natif NkapSDK v1.2 (« le tableau » + ardoise Jarvis) :
 * - Gestes v1.1 : circle, underline, arrow, write, frame, caption
 * - Gestes v1.2 : box, callout, num (①②③), highlight, strike, check (✓), cross (✗),
 *   et ardoise `notebook` (lines, flow, bars, table, choices)
 * - Convertit automatiquement les coordonnées écran (getLocationOnScreen) en coordonnées surface.
 */
class NkapOverlayView(ctx: Context) : View(ctx) {

    private val density = ctx.resources.displayMetrics.density
    private val surfaceOffset = IntArray(2)

    private val inks = mapOf(
        Ink.INK to Color.parseColor("#12233A"),
        Ink.YELLOW to Color.parseColor("#F5B700"),
        Ink.RED to Color.parseColor("#FF3B5C"),
        Ink.GREEN to Color.parseColor("#10B981"),
        Ink.CYAN to Color.parseColor("#38BDF8"),
    )
    private val outlines = mapOf(
        Ink.INK to Color.argb(185, 255, 255, 255),
        Ink.YELLOW to Color.argb(175, 18, 35, 58),
        Ink.RED to Color.argb(180, 255, 255, 255),
        Ink.GREEN to Color.argb(175, 10, 25, 20),
        Ink.CYAN to Color.argb(175, 10, 20, 35),
    )

    private val fontBold: Typeface by lazy {
        runCatching { Typeface.createFromAsset(context.assets, "fonts/Andika-Bold.ttf") }
            .getOrDefault(Typeface.DEFAULT_BOLD)
    }
    private val fontReg: Typeface by lazy {
        runCatching { Typeface.createFromAsset(context.assets, "fonts/Andika-Regular.ttf") }
            .getOrDefault(Typeface.DEFAULT)
    }

    private sealed class Mark {
        abstract val id: String
        abstract val startedAt: Long
        abstract val drawMs: Long

        class Stroke(
            override val id: String,
            val main: HandPath,
            val head: HandPath?,
            val color: Int,
            val outlineColor: Int,
            val width: Float,
            override val startedAt: Long,
            override val drawMs: Long,
        ) : Mark()

        class HighlightMark(
            override val id: String,
            val rect: RectF,
            val color: Int,
            override val startedAt: Long,
            override val drawMs: Long,
        ) : Mark()

        class FrameMark(
            override val id: String,
            val rect: RectF,
            val label: String?,
            val color: Int,
            override val startedAt: Long,
            override val drawMs: Long = 180,
        ) : Mark()

        class CalloutMark(
            override val id: String,
            val anchorX: Float,
            val anchorY: Float,
            val label: String,
            val color: Int,
            override val startedAt: Long,
            override val drawMs: Long = 220,
        ) : Mark()

        class NumMark(
            override val id: String,
            val cx: Float,
            val cy: Float,
            val step: Int,
            val label: String,
            val color: Int,
            override val startedAt: Long,
            override val drawMs: Long = 200,
        ) : Mark()

        class WriteMark(
            override val id: String,
            val text: String,
            val cx: Float,
            val cy: Float,
            val sizeSp: Float,
            val color: Int,
            val backing: Boolean,
            val perLetterMs: Int,
            override val startedAt: Long,
            override val drawMs: Long,
        ) : Mark()

        class NotebookMark(
            override val id: String,
            val nb: NkapAction.Notebook,
            val anchorY: Float?,
            override val startedAt: Long,
            override val drawMs: Long = 260,
        ) : Mark()
    }

    private val marks = LinkedHashMap<String, Mark>()
    private var captionText: String? = null
    private var captionSub: String? = null
    private var captionUpdatedAt: Long = 0L

    init {
        tag = cm.nkapmobile.sdk.context.ViewTreeScanner.OVERLAY_TAG
    }

    private fun now(): Long = SystemClock.uptimeMillis()

    private fun toLocalRect(node: ScreenNode): RectF {
        getLocationOnScreen(surfaceOffset)
        val ox = surfaceOffset[0].toFloat()
        val oy = surfaceOffset[1].toFloat()
        return RectF(
            node.bounds[0] - ox,
            node.bounds[1] - oy,
            node.bounds[2] - ox,
            node.bounds[3] - oy,
        )
    }

    private fun strokePaint(color: Int, widthPx: Float, isOutline: Boolean = false) = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        strokeWidth = if (isOutline) widthPx + 3.2f * density else widthPx
        this.color = color
    }

    private fun putMark(m: Mark) {
        synchronized(marks) { marks[m.id] = m }
        postInvalidateOnAnimation()
    }

    fun showCircle(node: ScreenNode?, color: Ink, drawMs: Int, id: String) {
        node ?: return
        val r = toLocalRect(node)
        val path = handCircle(r.centerX(), r.centerY(), r.width() / 2f + 10f * density, r.height() / 2f + 8f * density, id)
        putMark(Mark.Stroke(id, path, null, inks[color]!!, outlines[color]!!, 3.6f * density, now(), drawMs.toLong()))
    }

    fun showBox(node: ScreenNode?, color: Ink, drawMs: Int, id: String) {
        node ?: return
        val r = toLocalRect(node)
        val pad = 6f * density
        val path = handBox(r.left - pad, r.top - pad, r.width() + pad * 2, r.height() + pad * 2, id)
        putMark(Mark.Stroke(id, path, null, inks[color]!!, outlines[color]!!, 3.2f * density, now(), drawMs.toLong()))
    }

    fun showUnderline(node: ScreenNode?, color: Ink, drawMs: Int, id: String) {
        node ?: return
        val r = toLocalRect(node)
        val path = handUnderline(r.left - 4f * density, r.bottom + 4f * density, r.width() + 8f * density, id)
        putMark(Mark.Stroke(id, path, null, inks[color]!!, outlines[color]!!, 3.4f * density, now(), drawMs.toLong()))
    }

    fun showHighlight(node: ScreenNode?, color: Ink, drawMs: Int, id: String) {
        node ?: return
        val r = toLocalRect(node)
        r.inset(-4f * density, -2f * density)
        putMark(Mark.HighlightMark(id, r, inks[color]!!, now(), drawMs.toLong()))
    }

    fun showStrike(node: ScreenNode?, color: Ink, drawMs: Int, id: String) {
        node ?: return
        val r = toLocalRect(node)
        val path = handStrike(r.left, r.centerY(), r.width(), id)
        putMark(Mark.Stroke(id, path, null, inks[color]!!, outlines[color]!!, 3.4f * density, now(), drawMs.toLong()))
    }

    fun showCheck(node: ScreenNode?, color: Ink, drawMs: Int, id: String) {
        node ?: return
        val r = toLocalRect(node)
        val cx = (r.right + 16f * density).coerceAtMost(width - 20f * density)
        val path = handCheck(cx, r.centerY(), 22f * density)
        putMark(Mark.Stroke(id, path, null, inks[color]!!, outlines[color]!!, 3.8f * density, now(), drawMs.toLong()))
    }

    fun showCross(node: ScreenNode?, color: Ink, drawMs: Int, id: String) {
        node ?: return
        val r = toLocalRect(node)
        val cx = (r.right + 16f * density).coerceAtMost(width - 20f * density)
        val cross = handCross(cx, r.centerY(), 20f * density)
        putMark(Mark.Stroke(id, cross.main, cross.head, inks[color]!!, outlines[color]!!, 3.8f * density, now(), drawMs.toLong()))
    }

    fun showArrow(fromNode: ScreenNode?, toNode: ScreenNode?, color: Ink, drawMs: Int, bow: Float, id: String) {
        if (fromNode == null || toNode == null) return
        val a = toLocalRect(fromNode)
        val b = toLocalRect(toNode)
        val arrow = handArrow(a.centerX(), a.centerY(), b.centerX(), b.centerY(), id, bow)
        putMark(Mark.Stroke(id, arrow.main, arrow.head, inks[color]!!, outlines[color]!!, 3f * density, now(), drawMs.toLong()))
    }

    fun showFrame(node: ScreenNode?, label: String?, color: Ink, padDp: Int, id: String) {
        node ?: return
        val r = toLocalRect(node)
        val pad = padDp * density
        r.inset(-pad, -pad)
        putMark(Mark.FrameMark(id, r, label, inks[color]!!, now()))
    }

    fun showCallout(node: ScreenNode?, label: String, color: Ink, id: String) {
        node ?: return
        if (label.isBlank()) return
        val r = toLocalRect(node)
        putMark(Mark.CalloutMark(id, r.centerX(), r.top, label, inks[color]!!, now()))
    }

    fun showNum(node: ScreenNode?, step: Int, label: String, color: Ink, id: String) {
        node ?: return
        val r = toLocalRect(node)
        val cx = (r.left - 14f * density).coerceAtLeast(18f * density)
        putMark(Mark.NumMark(id, cx, r.centerY(), step, label, inks[color]!!, now()))
    }

    fun showWrite(text: String, node: ScreenNode?, sizeSp: Float, color: Ink, backing: Boolean, perLetterMs: Int, id: String) {
        node ?: return
        val r = toLocalRect(node)
        putMark(
            Mark.WriteMark(
                id, text, r.centerX(), (r.top - 22f * density).coerceAtLeast(36f * density),
                sizeSp, inks[color]!!, backing, perLetterMs, now(), (text.length * perLetterMs).toLong().coerceAtLeast(160L)
            )
        )
    }

    fun showNotebook(nb: NkapAction.Notebook, anchorNode: ScreenNode?) {
        val ay = anchorNode?.let { toLocalRect(it).bottom }
        putMark(Mark.NotebookMark(nb.id, nb, ay, now()))
    }

    fun showCaption(text: String?, subFr: String? = null) {
        captionText = text?.takeIf { it.isNotBlank() }
        captionSub = subFr?.takeIf { it.isNotBlank() }
        captionUpdatedAt = now()
        postInvalidateOnAnimation()
    }

    fun hideMark(id: String) {
        synchronized(marks) { marks.remove(id) }
        postInvalidateOnAnimation()
    }

    fun clearAll() {
        synchronized(marks) { marks.clear() }
        captionText = null
        captionSub = null
        postInvalidateOnAnimation()
    }

    override fun onDraw(canvas: Canvas) {
        val t = now()
        var animating = false

        synchronized(marks) {
            for (m in marks.values) {
                val elapsed = t - m.startedAt
                val prog = (elapsed.toFloat() / m.drawMs.coerceAtLeast(1L)).coerceIn(0f, 1f)
                when (m) {
                    is Mark.Stroke -> {
                        val p = trimmed(m.main.path, prog)
                        if (!p.isEmpty) {
                            canvas.drawPath(p, strokePaint(m.outlineColor, m.width, isOutline = true))
                            canvas.drawPath(p, strokePaint(m.color, m.width))
                        }
                        if (m.head != null && prog >= 1f) {
                            val hp = trimmed(m.head.path, ((elapsed - m.drawMs) / 180f).coerceIn(0f, 1f))
                            if (!hp.isEmpty) {
                                canvas.drawPath(hp, strokePaint(m.outlineColor, m.width, isOutline = true))
                                canvas.drawPath(hp, strokePaint(m.color, m.width))
                            }
                        }
                        if (elapsed < m.drawMs + (if (m.head != null) 200L else 0L)) animating = true
                    }
                    is Mark.HighlightMark -> {
                        val wCur = m.rect.width() * prog
                        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                            color = Color.argb(85, Color.red(m.color), Color.green(m.color), Color.blue(m.color))
                        }
                        canvas.drawRoundRect(
                            m.rect.left, m.rect.top, m.rect.left + wCur, m.rect.bottom,
                            6f * density, 6f * density, paint
                        )
                        if (prog < 1f) animating = true
                    }
                    is Mark.FrameMark -> {
                        drawFrame(canvas, m, prog)
                        if (prog < 1f) animating = true
                    }
                    is Mark.CalloutMark -> {
                        drawCallout(canvas, m, prog)
                        if (prog < 1f) animating = true
                    }
                    is Mark.NumMark -> {
                        drawNumBadge(canvas, m, prog)
                        if (prog < 1f) animating = true
                    }
                    is Mark.WriteMark -> {
                        val chars = (elapsed / m.perLetterMs.coerceAtLeast(15)).toInt().coerceAtMost(m.text.length)
                        drawWrite(canvas, m, chars)
                        if (chars < m.text.length) animating = true
                    }
                    is Mark.NotebookMark -> {
                        drawNotebook(canvas, m, prog)
                        if (prog < 1f) animating = true
                    }
                }
            }
        }

        if (captionText != null) {
            drawCaptionPill(canvas)
        }

        if (animating) postInvalidateOnAnimation()
    }

    private fun drawFrame(canvas: Canvas, m: Mark.FrameMark, alpha: Float) {
        val border = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 2f * density
            color = Color.argb((alpha * 170).toInt(), Color.red(m.color), Color.green(m.color), Color.blue(m.color))
        }
        val corner = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 3.5f * density
            color = Color.argb((alpha * 255).toInt(), Color.red(m.color), Color.green(m.color), Color.blue(m.color))
        }
        canvas.drawRoundRect(m.rect, 10f * density, 10f * density, border)
        val L = 14f * density
        val r = m.rect
        canvas.drawLine(r.left, r.top, r.left + L, r.top, corner)
        canvas.drawLine(r.left, r.top, r.left, r.top + L, corner)
        canvas.drawLine(r.right - L, r.top, r.right, r.top, corner)
        canvas.drawLine(r.right, r.top, r.right, r.top + L, corner)
        canvas.drawLine(r.left, r.bottom, r.left + L, r.bottom, corner)
        canvas.drawLine(r.left, r.bottom - L, r.left, r.bottom, corner)
        canvas.drawLine(r.right - L, r.bottom, r.right, r.bottom, corner)
        canvas.drawLine(r.right, r.bottom - L, r.right, r.bottom, corner)

        if (!m.label.isNullOrBlank()) {
            drawBadgeTag(canvas, r.centerX(), (r.top - 26f * density).coerceAtLeast(36f * density), m.label, m.color, alpha)
        }
    }

    private fun drawCallout(canvas: Canvas, m: Mark.CalloutMark, alpha: Float) {
        val cy = (m.anchorY - 22f * density).coerceAtLeast(38f * density)
        drawBadgeTag(canvas, m.anchorX, cy, m.label, m.color, alpha)
    }

    private fun drawBadgeTag(canvas: Canvas, cx: Float, cy: Float, text: String, accent: Int, alpha: Float) {
        val tp = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            typeface = fontBold
            textSize = 13f * density
            color = Color.parseColor("#FEF9EE")
            textAlign = Paint.Align.CENTER
            this.alpha = (alpha * 255).toInt()
        }
        val tw = tp.measureText(text)
        val padH = 12f * density
        val h = 28f * density
        val left = (cx - tw / 2f - padH).coerceIn(10f * density, (width - tw - padH * 2 - 10f * density).coerceAtLeast(10f * density))
        val rect = RectF(left, cy - h / 2f, left + tw + padH * 2, cy + h / 2f)
        val bg = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.argb((alpha * 238).toInt(), 20, 16, 12)
        }
        val bd = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 1.6f * density
            color = Color.argb((alpha * 235).toInt(), Color.red(accent), Color.green(accent), Color.blue(accent))
        }
        canvas.drawRoundRect(rect, h / 2f, h / 2f, bg)
        canvas.drawRoundRect(rect, h / 2f, h / 2f, bd)
        canvas.drawText(text, rect.centerX(), rect.centerY() + 4.5f * density, tp)
    }

    private fun drawNumBadge(canvas: Canvas, m: Mark.NumMark, alpha: Float) {
        val r = 14f * density
        val bg = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.argb((alpha * 245).toInt(), Color.red(m.color), Color.green(m.color), Color.blue(m.color))
        }
        val tp = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            typeface = fontBold
            textSize = 13f * density
            color = Color.parseColor("#140E07")
            textAlign = Paint.Align.CENTER
        }
        canvas.drawCircle(m.cx, m.cy, r, bg)
        canvas.drawText(m.step.toString(), m.cx, m.cy + 4.5f * density, tp)
        if (m.label.isNotBlank()) {
            drawBadgeTag(canvas, m.cx + 68f * density, m.cy - 22f * density, m.label, m.color, alpha)
        }
    }

    private fun drawWrite(canvas: Canvas, m: Mark.WriteMark, revealed: Int) {
        val sub = m.text.take(revealed)
        if (sub.isEmpty()) return
        drawBadgeTag(canvas, m.cx, m.cy, sub, m.color, 1f)
    }

    private fun drawNotebook(canvas: Canvas, m: Mark.NotebookMark, alpha: Float) {
        val nb = m.nb
        val cardW = (width - 28f * density).coerceAtMost(350f * density)
        val left = (width - cardW) / 2f
        val pad = 14f * density

        val titlePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            typeface = fontBold
            textSize = 14f * density
            color = Color.parseColor("#FDE68A")
        }
        val bodyPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            typeface = fontReg
            textSize = 13f * density
            color = Color.parseColor("#FEF9EE")
        }
        val valPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            typeface = fontBold
            textSize = 13f * density
            color = Color.parseColor("#F5B700")
            textAlign = Paint.Align.RIGHT
        }

        // Calcul de la hauteur selon le mode
        val rowCount = when (nb.mode) {
            "flow" -> 2
            "table" -> (if (nb.headers.isNotEmpty()) 1 else 0) + nb.rows.size
            "bars" -> nb.lines.size.coerceAtLeast(1)
            "choices" -> nb.choices.size.coerceAtLeast(1)
            else -> nb.lines.size.coerceAtLeast(1)
        }
        val lineH = if (nb.mode == "bars") 34f * density else 24f * density
        val cardH = 44f * density + rowCount * lineH + pad
        val preferredTop = (m.anchorY ?: (height * 0.48f)) + 16f * density
        val maxTop = (height - cardH - 94f * density).coerceAtLeast(56f * density)
        val top = preferredTop.coerceIn(56f * density, maxTop)

        val rect = RectF(left, top, left + cardW, top + cardH)
        val bg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb((alpha * 242).toInt(), 20, 16, 13) }
        val bd = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 1.4f * density
            color = Color.argb((alpha * 190).toInt(), 245, 183, 0)
        }
        canvas.drawRoundRect(rect, 16f * density, 16f * density, bg)
        canvas.drawRoundRect(rect, 16f * density, 16f * density, bd)

        var y = top + 24f * density
        canvas.drawText(nb.title.ifBlank { "Explication" }, left + pad, y, titlePaint)
        y += 10f * density
        canvas.drawLine(left + pad, y, left + cardW - pad, y, Paint().apply { color = Color.argb(65, 245, 183, 0); strokeWidth = density })
        y += 20f * density

        when (nb.mode) {
            "flow" -> {
                val flowText = nb.steps.joinToString("  →  ").ifBlank { nb.lines.joinToString(" → ") { it.text } }
                canvas.drawText(flowText.take(46), left + pad, y + 6f * density, bodyPaint)
            }
            "bars" -> {
                val maxVal = nb.lines.mapNotNull { it.pct }.maxOrNull()?.takeIf { it > 0f } ?: 100f
                for (ln in nb.lines) {
                    val accent = inks[ln.color] ?: Color.parseColor("#F5B700")
                    canvas.drawText(ln.text.take(28), left + pad, y, bodyPaint)
                    if (ln.value.isNotBlank()) canvas.drawText(ln.value, left + cardW - pad, y, valPaint)
                    val barY = y + 6f * density
                    val barW = cardW - pad * 2
                    val raw = ln.pct ?: (maxVal * 0.65f)
                    val ratio = (if (maxVal > 100f) raw / maxVal else raw / 100f).coerceIn(0.08f, 1f)
                    canvas.drawRoundRect(left + pad, barY, left + pad + barW, barY + 7f * density, 4f * density, 4f * density,
                        Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(40, 255, 255, 255) })
                    canvas.drawRoundRect(left + pad, barY, left + pad + barW * ratio * alpha, barY + 7f * density, 4f * density, 4f * density,
                        Paint(Paint.ANTI_ALIAS_FLAG).apply { color = accent })
                    y += lineH
                }
            }
            "table" -> {
                val cols = (nb.headers.size).coerceAtLeast(nb.rows.firstOrNull()?.size ?: 2).coerceAtLeast(1)
                val colW = (cardW - pad * 2) / cols
                if (nb.headers.isNotEmpty()) {
                    val hp = Paint(titlePaint).apply { textSize = 11.5f * density }
                    nb.headers.forEachIndexed { idx, h -> canvas.drawText(h.take(16), left + pad + idx * colW, y, hp) }
                    y += lineH
                }
                for (r in nb.rows) {
                    r.forEachIndexed { idx, cell -> canvas.drawText(cell.take(16), left + pad + idx * colW, y, bodyPaint) }
                    y += lineH
                }
            }
            "choices" -> {
                nb.choices.forEachIndexed { idx, c ->
                    canvas.drawText("${idx + 1}. $c".take(42), left + pad, y, bodyPaint)
                    y += lineH
                }
            }
            else -> {
                for (ln in nb.lines) {
                    if (ln.divider) {
                        canvas.drawLine(left + pad, y - 6f * density, left + cardW - pad, y - 6f * density,
                            Paint().apply { color = Color.argb(55, 255, 255, 255); strokeWidth = density })
                        y += 12f * density
                        continue
                    }
                    val p = Paint(bodyPaint).apply {
                        if (ln.bold) typeface = fontBold
                        color = when (ln.color) {
                            Ink.YELLOW -> Color.parseColor("#FDE68A")
                            Ink.RED -> Color.parseColor("#FDA4AF")
                            Ink.GREEN -> Color.parseColor("#6EE7B7")
                            Ink.CYAN -> Color.parseColor("#7DD3FC")
                            else -> Color.parseColor("#FEF9EE")
                        }
                    }
                    canvas.drawText(ln.text.take(40), left + pad, y, p)
                    if (ln.value.isNotBlank()) canvas.drawText(ln.value, left + cardW - pad, y, valPaint)
                    y += lineH
                }
            }
        }
    }

    private fun drawCaptionPill(canvas: Canvas) {
        val txt = captionText ?: return
        val maxW = width - 36f * density
        val tp = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            typeface = fontBold
            textSize = 14.5f * density
            color = Color.WHITE
            textAlign = Paint.Align.CENTER
        }
        val words = txt.split(" ")
        val lines = ArrayList<String>()
        val cur = StringBuilder()
        for (w in words) {
            val test = if (cur.isEmpty()) w else "$cur $w"
            if (tp.measureText(test) > maxW - 28f * density && cur.isNotEmpty()) {
                lines.add(cur.toString()); cur.clear().append(w)
            } else {
                cur.clear().append(test)
            }
        }
        if (cur.isNotEmpty()) lines.add(cur.toString())

        val lineH = 20f * density
        val pillH = lines.size * lineH + 20f * density
        val pillW = (lines.maxOfOrNull { tp.measureText(it) } ?: 120f) + 32f * density
        val left = (width - pillW) / 2f
        val bottom = height - 74f * density
        val rect = RectF(left, bottom - pillH, left + pillW, bottom)

        val bg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(220, 12, 16, 26) }
        val bd = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 1.2f * density
            color = Color.argb(120, 245, 183, 0)
        }
        canvas.drawRoundRect(rect, 18f * density, 18f * density, bg)
        canvas.drawRoundRect(rect, 18f * density, 18f * density, bd)

        var y = rect.top + 22f * density
        for (l in lines) {
            canvas.drawText(l, rect.centerX(), y, tp)
            y += lineH
        }
    }
}
