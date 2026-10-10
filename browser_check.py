"""Deterministic interaction checks in installed Edge, with prediction responses stubbed."""
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

from config import PORT


def main():
    root = Path(__file__).parent / "test-artifacts"
    root.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        requests = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url))
        calls = []
        polls = []
        scenario = {'confidence': .83, 'conflicted': False, 'mode': 'single'}
        def prediction(route):
            calls.append(route.request.post_data_json)
            route.fulfill(status=202, json={"id": "browser-test", "state": "stirring"})
        def result(route):
            polls.append(True)
            if len(polls) == 1:
                route.fulfill(json={"id": "browser-test", "state": "stirring", "result": None})
            else:
                route.fulfill(json={"state": "revealed", "result": {"verdict": "PROBABLY", "probabilities": {}, "vibe": 1.5, "quip": "Probably, but the dial-up modem is judging you.", "hint": "", "mutters": "", **scenario}})
        page.route("**/api/predictions", prediction)
        page.route("**/api/predictions/browser-test", result)
        page.route("**/api/rescan", lambda route: route.fulfill(status=202, json={"status": "scanning"}))
        page.goto(f"http://127.0.0.1:{PORT}")
        initial_float = page.locator('#orb-motion').evaluate('el => el.style.transform')
        initial_fog = page.locator('.fog').first.evaluate('el => el.style.transform')
        page.wait_for_timeout(600)
        assert initial_float != page.locator('#orb-motion').evaluate('el => el.style.transform'), 'Idle float must move'
        assert initial_fog != page.locator('.fog').first.evaluate('el => el.style.transform'), 'Murk must drift'
        page.locator("#question").fill("Should I text them back?")
        orb = page.locator("#orb")
        bounds = orb.bounding_box()
        x, y = bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + 2, y)
        page.wait_for_timeout(150)
        page.mouse.up()
        page.wait_for_timeout(500)
        assert not calls, "Weak motion should not request a prediction"
        assert "barely felt" in page.locator("#status").inner_text()
        orb.focus()
        page.keyboard.press("Space")
        expect(page.locator('#room')).to_have_class(re.compile(r'.*\brevealed\b.*'))
        expect(page.locator('#quip')).to_have_text('Probably, but the dial-up modem is judging you.')
        assert len(calls) == 1 and calls[0] == {"question": "Should I text them back?"}
        assert "83%" in page.locator("#confidence-note").inner_text()
        assert page.locator('.candle.lit').count() == 6
        assert '6 of 7' in page.locator('#candles').get_attribute('aria-label')
        expect(page.locator('#triangle')).to_have_css('opacity', '1')
        page.screenshot(path=str(root / "p2-desktop.png"), full_page=True)
        with page.expect_download() as saved:
            page.locator('#save-card').click()
        saved.value.save_as(str(root / 'prophecy.png'))
        import struct
        png = (root / 'prophecy.png').read_bytes()
        assert png[:8] == b'\x89PNG\r\n\x1a\n'
        assert struct.unpack('>II', png[16:24])[0] == 1200
        page.evaluate("Object.defineProperty(navigator, 'canShare', {configurable:true, value: () => true}); Object.defineProperty(navigator, 'share', {configurable:true, value: async data => { window.sharedCard = {name:data.files[0].name, size:data.files[0].size, type:data.files[0].type}; }});")
        page.locator('#share-card').click()
        assert page.evaluate('window.sharedCard.type') == 'image/png'
        page.evaluate("Object.defineProperty(navigator, 'share', {configurable:true, value: async () => { throw new DOMException('Cancelled', 'AbortError'); }});")
        page.locator('#share-card').click()
        assert page.locator('#share-status').inner_text() == ''
        page.locator("#gear").click()
        page.locator("#settings").wait_for(state="visible")
        assert page.locator("#voice-model").input_value() == "nemotron-3-nano:4b"
        assert "Canned quips" in page.locator("#voice-model").inner_text()
        assert "cloud" not in page.locator("#voice-model").inner_text().lower()
        assert not page.locator('#sound').is_checked()
        # A Space press while settings are open never shakes the orb.
        page.locator("#rescan").focus()
        page.keyboard.press("Space")
        page.wait_for_timeout(450)
        assert len(calls) == 1
        page.locator("#close-settings").click()
        polls.clear()
        page.mouse.move(x, y)
        page.mouse.down()
        for i in range(16):
            page.mouse.move(x + (65 if i % 2 == 0 else -65), y)
            page.wait_for_timeout(30)
        page.mouse.up()
        expect(page.locator('#room')).to_have_class(re.compile(r'.*\brevealed\b.*'))
        page.wait_for_timeout(700)
        assert len(calls) == 2, "A real drag shake must trigger once"
        expect(page.locator('#quip')).to_have_text('Probably, but the dial-up modem is judging you.')
        page.emulate_media(reduced_motion="reduce")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(300)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.locator("#orb-motion").evaluate("el => getComputedStyle(el).transform") == "none"
        assert page.locator('#question').bounding_box()['y'] > page.locator('#orb').bounding_box()['y'] + page.locator('#orb').bounding_box()['height']
        page.screenshot(path=str(root / "p2-phone-reduced-motion.png"), full_page=True)
        page.set_viewport_size({'width':320, 'height':740})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        counts = page.evaluate("async () => { const {candleCount} = await import('/static/share-card.js'); return [null,0,.5,1].map(candleCount); }")
        assert counts == [0,0,4,7]
        audio = page.evaluate("async () => { const {OrbSound} = await import('/static/sound.js'); const sound = new OrbSound(); sound.unlock(); const defaultSilent = sound.context === null; sound.setEnabled(true); sound.unlock(); await sound.context.resume(); sound.intensity(.8); sound.reveal(); const running = sound.context.state; sound.setEnabled(false); await sound.context.suspend(); const paused = sound.context.state; await sound.context.close(); return {defaultSilent,running,paused}; }")
        assert audio == {'defaultSilent':True, 'running':'running', 'paused':'suspended'}
        page.emulate_media(reduced_motion='no-preference')
        scenario.update(confidence=.5, conflicted=True)
        polls.clear(); orb.focus(); page.keyboard.press('Space')
        expect(page.locator('#room')).to_have_class(re.compile(r'.*\bconflicted\b.*'))
        assert page.locator('.candle.lit').count() == 4
        page.wait_for_timeout(1200)
        flame_before = page.locator('.candle.lit .flame').first.evaluate('el => el.style.opacity')
        page.wait_for_timeout(160)
        assert flame_before != page.locator('.candle.lit .flame').first.evaluate('el => el.style.opacity')
        scenario.update(confidence=None, conflicted=False, mode='dice-only')
        polls.clear(); orb.focus(); page.keyboard.press('Space')
        expect(page.locator('#status')).to_have_text('Dice only · the oracle is unavailable.')
        assert page.locator('.candle.lit').count() == 0
        assert 'no model confidence' in page.locator('#candles').get_attribute('aria-label').lower()
        wrapping = page.evaluate("""async () => {
          const {wrap} = await import('/static/share-card.js');
          const ctx = document.createElement('canvas').getContext('2d');
          ctx.font = 'italic 36px Georgia';
          const sample = 'Yes, but also no—it’s the gas station’s fault for selling it as both.';
          const lines = wrap(ctx, sample, 950);
          const narrow = wrap(ctx, 'both both', ctx.measureText('both').width + 1);
          const long = wrap(ctx, 'x'.repeat(150), 100);
          return {lines,narrow,longFits:long.every(line => ctx.measureText(line).width <= 100)};
        }""")
        assert wrapping['narrow'] == ['both', 'both'], wrapping
        assert wrapping['longFits'], wrapping
        assert ' '.join(wrapping['lines']) == 'Yes, but also no—it’s the gas station’s fault for selling it as both.'
        for width in (320,390,1280):
            page.set_viewport_size({'width':width,'height':900})
            page.wait_for_timeout(200)
            fit = page.evaluate("""async () => {
              const {fitVerdict} = await import('/static/ui.js');
              const {VERDICT_LABELS} = await import('/static/verdict-label.js');
              const triangle = document.getElementById('triangle'), label = document.getElementById('verdict');
              const failures = [];
              for (const text of Object.values(VERDICT_LABELS).flat()) {
                label.textContent = text;
                triangle.classList.toggle('long-label', text.length > 12);
                fitVerdict();
                if (label.scrollWidth > label.clientWidth || label.scrollHeight > label.clientHeight) failures.push(text);
                const outer = triangle.getBoundingClientRect();
                const range = document.createRange(); range.selectNodeContents(label);
                for (const rect of range.getClientRects()) {
                  const halfWidth = outer.width * ((rect.top - outer.top) / outer.height) / 2;
                  const center = outer.left + outer.width / 2;
                  if (rect.left < center - halfWidth - 1 || rect.right > center + halfWidth + 1 || rect.bottom > outer.bottom) failures.push(text + ': polygon');
                }
              }
              return failures;
            }""")
            assert not fit, (width,fit)
        assert not errors, errors
        external = [url for url in requests if not url.startswith(f"http://127.0.0.1:{PORT}/") and not url.startswith("data:")]
        assert not external, external
        report = {"checks": ["idle float moves", "murk drifts", "weak shake ignored", "Space triggers exactly once", "stirring then reveal", "question-only request", "Nemotron selectable default", "six confidence candles at 83 percent", "confidence rounding and dice unknown", "PNG download width 1200", "native file-share dispatch and cancellation", "local selectors", "settings suppress shake", "drag triggers exactly once", "mobile question below orb", "390 and 320px layouts fit", "reduced motion", "no JS errors", "no external requests"], "prediction_requests": calls, "js_errors": errors, "external_requests": external}
        report['checks'] += ['whole-word card wrapping including both', 'oversized token wrapping', 'all grouped labels fit triangle at 320,390,1280px']
        (root / "browser_checks.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        browser.close()
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
