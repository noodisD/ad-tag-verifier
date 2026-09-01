"""
Channel Factory (YouTube force_ad_encrypted) + Illumin (acuityplatform.com banners)
Campaign: BTS 2026  |  Campaign ID: 90000001
Check: ad.doubleclick.net/ddm/trackimp/.../B90000001.{placement_id}
"""
from playwright.sync_api import sync_playwright
import time, sys, re

CAMPAIGN_ID = "90000001"
UA_D = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

CF_ROWS = [
    ("6s_stationery", "900000022", "https://www.youtube.com/watch?v=VSCkrvtVt3Y&force_ad_encrypted=AKjQQ4LT30iHKYF5ewk41_3PP5f4DOSjWX-2INIHU5RuSQXpxtwfQ_Z-zIqsnnkh5OvpAv2N0xqhAhjOJ5y3aFniSMILzMvv3Dcs0kgA44ZpZ3r7pby47Eq4ZpwS5TFtiluw6N6FUzE266Y6-eRCmbuQLrSWaS8mjrfN1uha1018pKfItyxX7aGl7iQeoir-JjrNp6cTJ5TsSulE5hJlwSTW5Fs3OUyQ-DpXrywx8B3UeweuQBekj7xQ1xUAy3OV4b8v9FaNkIFrUjU4DRakYgRsDGx5kRnqhjUoK6xrkYiO30Fi2CY0FZVCGZ-1TPJ1Mj_5SmhxzK9QCSRlC4TVpAlIlgELek-zcqJbyEnXE5pwkps7kPPTEutDxVZrjRBdKGZCDU0DK62noALidxJatizHQD30-M6iTmmGn_6SmslngYoLvvJNUN69wmicQCAo89zbNta_QzjrCzzX6Is_irgGUE-GMvtq-pyrHi8ZQpHPXftx969uo-9V9jvxXl5Cdl1LgSoRARjljgYh0qP5AdakFnJyjTSiBrIx-YP57pbE7KkL5bLhTqnL8xqFf455vvDQdEiorsii7FgFHd4nNK6Iv0s1YCVUcZ6e-VME8-S9VfHLn_6OxXdHDqgp2Q7uzTMnFucqg0__1oCeEJ8ywNDuZ7MWecBSy4fdp621n4tt7GLws9zCllH6vnBeHgRjbRISI2mDK9e6lWh5NIGGbiq7NBjhpMNGwIVcp0RLVTmVeVlZ8jZR5DpHpjnpCjqZWRMnd87XOjK8pZ5z9p5IclUfiw-uOs0_WYHeBIhMx4rEkGhguVv_rs19ytWAEm8YNzTzPbsFcrI49S5lLwnRIV71iP8rWuk10DLe0t7cJ-ZPx4WstK_OdtyQpugYNmklsBTiXDB7wSgsxamHy37PV7Cn5fMj-GRrHAyQc_Noj7BQ_DeVVQ-azHtm7Gri-YOG-0LLCvdgxudDLhXB0txDWEKJOEClZI_o3PpCIgUgWMDPVhlciNYzFIZoqk36IbSxWTI9IF_D9ClX1I0I8lCT13yOMMoEA7ax6vRlTgnj_ZG8F9xMxq-w1rekEISvd7ZYg8Y7fIcvSobjdBw8G0an1WJ3gfxsyql8Kd4e3gGCmf1oq5v_W6AJoKjtQzSu3EVMmX6PNTB8L2Tb2prJnTLEbXIRj0w_HrJb7A=="),
    ("6s_clothing",   "900000022", "https://www.youtube.com/watch?v=VSCkrvtVt3Y&force_ad_encrypted=AKjQQ4K2PMrsf9kZTfSyz0bbXFOZ_KpOBRdnVYHsFeJ5yxZgbp-PhVjjpPhIK1TCKt7UD18ehtcJUbJuSTr-ee0AJsLIwpmpJRDPU5Atpxv-dlCfCRT5eGALvITzB9v2_S2O3humR11BuSs2_JyGTU1j35gMt_4W8RBZb9yIlcZflCn3CfEzTkhPdBwiwuMqtmdMzH-6Nfxr2toLpmfVZgEAP_lH6bp1qGLUbouuJHaAZaLoQG2fCos0pt9Ic7vxoibLOBmKC3Cxw8WHhMtOc2DyCMlOz_HB1nd_-RXczcqugqEVapgjEYg_9VPOzBspN9cVRK785BIsJo47FX9ikq5SQnTj7NeUON2dKpvVjRYMDYyFxm8cN5ORfG2OfurCHqipOVIz_xQc3sguRBQtDGgE3J780dN92wGoKBrV9LwDWQKhx4fOMRxxNu2_pJiQKyigYZ9nt39-WVzvsEG4hWmjTr1nXAtz31GJpdWhxLvI2AwA1dKpOPvUn7gEvsYIP71WqJOIV6_Na-MKJVF-84jdspXnyAu_uO55na0PK6_jGRUAxKeekDXScHUO1q932nnA1y70vlMKLhUohdooWanmpoP5SIDm-Fc9_bDXbPhc2edI3SNjz_Ld-L3QI8ULbSJ2-fa34lp2MlRlu7-IztQVvSpTWJPtEulPHYTCU0st1lNAauWZSYHNWrVPbJZzeEz33-ZweQz69U6zvNqIfo6CAUwFIKC5BsVmEFIEioWii1wXhhcAPDiblz4eMIKO3BLrFD3571sjyVL1gDhg8v7DpF5yaW-SEUGBWiFJ-f6cxlZRUVP3gt3mJkCIn4twdVj_cskeR4dJhsLiWIjhy_wrSucFhb9fbUk_F3yarBGNkryPyylYQOs74YsWn22mOdAbO4hZ1XC1BLnHLMt0RKGQD3Kpy7Feh4KoqwmpnlZd09loEsZXclJsYVBemraJql-NHmYW0-mpeVOjSih02CXIX3jMYt90eA7rL4el4ziGsDZdazFySus0NjuC8xBphDeKKxDqq75ndRNFy9f5Gh8iXP0XaSl19O0iF_KU1jswhwIhTv6ewTtzwAzN7A0wIWVZXz4HdQpKclorrVKr3UuMPrKEPzPrOQX304y0AbPYO48dPoswOsyH4ZVzTr7yORcJXhBEEtGIR5T-3bCuuVwCgRwR3zJIDw=="),
    ("30s_image",     "900000035", "https://www.youtube.com/watch?v=VSCkrvtVt3Y&force_ad_encrypted=AKjQQ4II5PLq_MH_T8t9mTdma-JIra00cWT3dSh_qqBECUsMOHtMfYvgYlXVI9xT4It4NxTl5E74i4B5ksy4pJ2tLyTmViHEqpnArqRQPttWNz2pfyCDobUkqLQ5_mjtfmwIwNeJwuiPgnrUI-eofjk0lbJ6FWe2xC3H22r94aQXcJ-AdIp5_4L0q8VbE74swKJbouqQm2pHQNpsDINd2Bg_-pTG0QZBxb0cDO9vsnFLmH3LkHcYXxTXesqE3fkW26hdhIt2VD3E_XbAIg_geLkCcKQvXuQnyY7mHKnucs0iq2t-cUObsUH6mDhl3453pKs8p6Euw7J1UkBbIyxUk4Z0-DccmTvevZ6n4A0GlWBA1TucvYKlAhl-PmPjE33NAxEPQYezKRcYyn2kwzsEJiLxYLrUzt4JdyHy522CWNF5ibN1a-qpJ1A7YkmXZvpaKJtX1TTEiQ16SIGARfFMXzsK1CgOzJt-i5Fwj4Q-Qon_6rbPezxD9NepH-vIOninYloX9LQATbNKGZkuqBIhxzRJ5M8bA7CNH9kXTwwYMp6KDrFNX_kOw7-XGZKP--VXEauAz7ske_YxhSImP2oUdH7xxkU9B3-ZdeT654DKKIXPiwGvWVjlkDi4u2sUrGcIYx2ySfyK-OXaqGePpK7k8MFmCGAfpK7YZUJAWaRsXasCW8hkRPvEhVm8JUwraItqmrppwrRKLan1LCl8WVgrvOWTE6MheX9-W0wxr3lIDYZ0XbkvoCeKJe0J64OEh0dLSTVnPpFqBNp3-B9wb9QfYQg_Xk4IoxQyjTgFMybgjXivqZZICKwQRjYrVywhc-CxveRKL4yiQ3HWW1-W5Fs81n-_hrQtXtGEl0dnIchIsA2yJQahCLbX-t3rDAbn0E6JOlk0BsxIMsKsHL4TJOF1xtaruJP9aSpM7E_Urd6qKhBr460P-jAKi4fDc6RyERLbL_quqztYjN-v0kY8bhTxQ7H_HKo0nZV412Nx6t7v1whpHyCbWCgkAUNU-IR_XEUgenTeZVttNHMMdgTJRTMpowYlbevRM-WIx_qeaTU0WHAfj7tFdDEeSJhI6n3kXwWQ-F5-jkev8UlMboGrl7D_0dSpewsYxB9460DgzOzTGmvi1UooknwxtDKFJYbw5pYw_hFDnznP6GJhYMrzMBsyw0TtCx3MnUJtjw=="),
    ("15s_product",   "900000035", "https://www.youtube.com/watch?v=VSCkrvtVt3Y&force_ad_encrypted=AKjQQ4IrIfoQJ1qIGTD_ZL00VfH6OmYlws2HISbqH0Eiw70YUxEmZPxgM1hDoLQLuC8dA_tCujEWu6yLVGUfHLzsgipuHsS-zx-ibEq9fxLuAZhHZMkQKTdOB9jVSg025_s0kg8fyKeXXJRyYGgn8s_4NRTXQkSevFcJHJkxvPoZiacmTAJkG7yFOOXOrVzqHFDgDD2k58nK6m1axTi2rh1HFT5_ByC4tI7sDfVG7zEgP-9c7hRejjdeR-_wMQp93SmfXCpcflDdzgLAkFBcTCnCRw-fbnFUqjlxhLANllBF7xErzNtY739j1c_jXgMeG6t4PFTDGuFkDNd_iKZyeY9V9fJ_Zmr6wTvwVl3zwCd1jDCxGK-6syIJGc6vexFhlZstDxNwzC_eg7QjfMSPJo-Vi1QV035GJJopeDqD72UQHaD-akwoc594PrWhZJoy_MQuC_GZ5rSv2kgjJVW9zibs7zYBzC3XK7qIlsRRBu06kZMxmcWGxXrVRujnT4K-4_DVNAQhnG3FsLXhFcrTpoS6zRxLkQWAahjWxmxcU5W0DERs0XGN97U77OVJhgXl99duWnFTvbkN-svfECYh9pI4rZ8heHuGCnc0coIJgg_LDoq-YNj0LaF6gPPXUkNZY9kxIfhaj1MrDNhdUEFJfIeYDFx1BD1hHn2n-oftrrN1zzBAe8B6FMEISZ6P-O0vmv0ZEGL4zArbNgJpT07luLzGd9v8ts9Gn0zo2WSxi323xHLwva1PCpbVFjjje6AO9h80igM_4jJO8doHmpVGKWyUhbBlT4x_zxZVcc7lZy1K9Ov53OEuTVWgjMXvyiQm7ukUffGGUUBYPSP0RkqSomk11g0e7yhtqVjaY0-Li1WqAWnZUR2HR_MqrZ8MD2zDPt3mOvUa-wqTahLs77vnSe2WKC7i3CNC_QF67l0WQpRUIv6aStlDJoW69nNVZarfjTKGa_nN0HJ7bYEfc3qvoF_Vq7VKGmUa4BkqOpqIIbCk1BrhA52aaGCjMFM135hDhyteW3v9gbcIp6C_Ih_AC7-aej070ZSO_p9MW174KJw0qPwK9y5jrX2RYnrjpcNoOxXemLsBzDiUuW_Z8GUYbImBPOGkfZk-Kq1YvFtXOTEW67hbMCGjeryQVfV5tvIjIDLnLxd721aQmRlezI55bOHkGuw5VdcAPw=="),
    ("30s_pion",      "900000035", "https://www.youtube.com/watch?v=VSCkrvtVt3Y&force_ad_encrypted=AKjQQ4JMw9pY_O619sNZ3YR5BYTgIfMyF0LroSlaOk7Cp_fhPhn81_jyecx6x-tAuHVu6oc_i1zkpqGpSIRvfizN3ExpwJTBcwJzHWBVVaLPSh5x7hqUEAHEwIpppUrsq7T56vGR4JBDcMg5Pb7JxJUpHcrDLcaRP7VLYxlVehfG7qp5ubVJgKFsHmucQAJwomTxk8-3knHkRk7k5t4N6kkSxvsQR2ibPtwn9oYfn0kXCZDhT52QftB4CxtJIc25Pmeuwa4EqLnnPHtsz3WiEeaMKgiI46kLg-XStRi4xaPUpnEIZZcu4BnC5DkxcI5m0qiw5-so63r-xhhwH2Oq3Ev2s97VRJykIdNv2y7Ua1N0C3wfc61BednDEw3561pFDrfVSwtqgD_kX8Cp5wFdwiAw7Dogt3RCC2asTC_nF26ybZaV7ziGqtCE56nxogT3csOMnmxqynOXWbtoJrKd56T46roJRWJ23BoAZrX7jlD-D2vbO-BJbxnB41ZF3GQ1Z9SPkvLzgvHIDXFoFaU9Upj4s9Qga7QYKKD9Jx2SfINrHe2o5J_ZOmoK-M2nYvBUcEvftcnvILCe-R-njrmhsWUoL5Zhkg0IsTMNfJfW1wFer9HkzJaFutseiwzN16cQmTT6qh_21KwA7NxZn54cYQdhttgg-9XeEQUeRmkb0VKcGb15KLp38HSSI6jW1OdquTpANO5sqvOrgoiwTCe-iPdM3gFBcrbfYP9Fs0DfPZBrCmq2PNs1luwJ3JNrM8tKqWy7d6N2CoRadYA6AOsBRejfbzu4MsMD6ccESr2Z7xsMx02DKEJFpdBGjWnPnVXZzK_A4OPOVVwPf0y1kgVgA5cZQSU9btDIqbLYR9LI2RWexxf1eAZV-JzcJXLnOG6weeJrhJPe2Vl8Rt-j-6y3rqq3KTKcJdSdFfhWGTyjFNI28T7MuU-UpaziXZprlzMoM7s86fdN5Fvg1EBTPgYzXlrZdzVsjvOgPqT-_nkCxqj72aYdkW1xnWk5R9lPIYjpT4dXDHj9YDtMclohjwTVyy0BMcsCDzEjyJykALAe6JXPcioJ1O1eNpBgOVIrUs4ODC_2IjSCshAFOpu-yDhslgx2F2KEZAVfiwnsELkQxkUruWfvkQlgIrD2wrty6-AJc2ywDt7Ze1yIcH6NBuJKPx4FWrt-DYBTEQ=="),
    ("15s_pion",      "900000035", "https://www.youtube.com/watch?v=VSCkrvtVt3Y&force_ad_encrypted=AKjQQ4I8g_uBLre9P6c34r7y5ioMgtajr3jnawoJlCj3pqw5rkjY1tYFADy-hsLTpkb0zra6luEaNazaoPS6D-GVL0-d7XRtA-oDZ6p9-VtcPMjLWoYn2qNjtK_2Q4VxKZ605FSbz0cKh0VTpOKvo6aj6TCiEvVbiyybCRf9PCEWV0Ain3MwI65I7BcjTBOmLSJYTV2HXfD4mkW47v3kWFzY8wcUmAvSPEujmGVioKH9ZCiixV4enG51nksSSQeSigbyifNbua1TQTp8f83bfFqaHbkAPJ-uFvTes7-VVc2kynfrw86jVnHt_xwg46IGP8uKDlxmYmYsEulmk-mV1zEm9O4eeXCvQFxaZjFarMR6lWPEa5av6JczelGr6_t8krTMdhohdXnzbkKV9pa6RqTSjke7GxDq2fVQPi8Vdwz3TpmlhYeaNXP-RA6f8Gq3BwKyHRMuNFQ__Z_Xec6P72Dpqkwll2xdZyX-WRDh5POIC5ebalcaAyxddWTXLRHInunGchHhlehsqh89Ix0dkIvd2IIsZOy99GybNPZRN9XrzW4rtt10JGngKcZCuoR9qnukI6Kj0uyjtAEzgjgYndYQIofMgdL26lj0LcZSpicFYRWdR4-MJ4TYcIWmC2RS4KxD8IpwjOxnqSWLnOfceANocK64LwnXTd1aQTu8J49hTOK5FHNRvUQ_bVa6eq51ugON_ZTNa7dswFslixaG5pJJK98sjK2QXFK9vbMLelwmQMp9o0vgbtMidzgxv4jsGoUil9zPSG6oaUebQ8t1pW6NB0uYTsvsxLMaTCnjMfYAK62MqYMIH2m4T5CEZvEDLjCUxszuVWRpyH9-VPz8Q6Lhi6sftZDBnOGpEPe24qw_JiWonQTzj8mbadslifz1DWLxmFYKl1m6j6eg544rmtB9oRPh5EtiDP_bpd3LDi05DCVPzHvrG1Sdq7u94LmKroHeck4QvrU9if3M_ktz1fNRRyCKYRMe_IIfXYeFEYQjU4WMGrJJ-GCKNsB2ZALLFrvzIW2Q-KlLd5gbMIDTErrqTpcjiYn94wGs7SjTk6COdFh1G_VPdxnO-HULo5ihDcD9nQbmnMy7Rd4cm7OdQxsDEBxju3pI0hCh_0jZXauGoLNYgGClSIUPxfhpgoLRJFW9XvVdUYIMQ70FYm1Z40Zu23eu3zucHg=="),
]

ILLUMIN_ROWS = [
    ("970x20",  "900000049", "https://acuityplatform.com/Adserver/creative/if?bannerid=3013799&adchoice=true"),
    ("700x300", "900000049", "https://acuityplatform.com/Adserver/creative/if?bannerid=3013795&adchoice=true"),
    ("950x200", "900000049", "https://acuityplatform.com/Adserver/creative/if?bannerid=3013797&adchoice=true"),
    ("320x480", "900000049", "https://acuityplatform.com/Adserver/creative/if?bannerid=3013787&adchoice=true"),
    ("300x600", "900000049", "https://acuityplatform.com/Adserver/creative/if?bannerid=3013785&adchoice=true"),
]

def accept_consent(page):
    phrases = ['Zaakceptuj wszystko', 'Akceptuję', 'Accept all', 'Agree to all',
               'I agree', 'Przejdź do YouTube', 'Got it', 'AKCEPTUJĘ']
    try:
        ok = page.evaluate("""(p) => {
            for (const el of document.querySelectorAll('button,a,tp-yt-paper-button,ytd-button-renderer')) {
                const t = (el.innerText || el.textContent || '').trim();
                if (p.some(x => t.toLowerCase().includes(x.toLowerCase()))) {
                    el.click(); return t;
                }
            } return null;
        }""", phrases)
        if ok: return True
    except: pass
    for sel in [
        "button[aria-label*='Accept']",
        "button[aria-label*='Zaakceptuj']",
        ".eom-button-row button:last-child",
        "[class*='consent'] button",
        "form[action*='consent'] button[value='1']",
    ]:
        try:
            if page.locator(sel).first.is_visible(timeout=600):
                page.locator(sel).first.click(); return True
        except: pass
    return False

def make_listener(flags, t_ref, pid, label):
    def on_req(req, _f=flags, _t=t_ref, _pid=pid, _l=label):
        u = req.url
        if 'doubleclick.net' not in u and 'dc_trk' not in u: return
        t = time.time() - _t[0] if _t[0] else 0
        pid_ok = _pid and _pid in u
        if 'trackimp' in u and not _f["imp"]:
            _f["imp"] = True; _f["imp_url"] = u[:180]
            print(f"    [IMP t+{t:.0f}s] {'PID_OK' if pid_ok else 'PID_MISS'} {u[35:120]}")
        elif 'trackclk' in u and not _f["clk"]:
            _f["clk"] = True
            print(f"    [CLK t+{t:.0f}s] {'PID_OK' if pid_ok else ''}")
        elif 'doubleclick.net' in u:
            print(f"    [DC  t+{t:.0f}s] {u[:100]}")
    return on_req

log = open("chanfac_illumin_results.txt", "w", encoding="utf-8", buffering=1)
class Tee:
    def __init__(self, *s): self.s = s
    def write(self, d):
        for x in self.s:
            try: x.write(d)
            except: pass
    def flush(self): [x.flush() for x in self.s]
sys.stdout = Tee(sys.__stdout__, log)

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    # ── Channel Factory (YouTube) ────────────────────────────────────────────────
    print("="*65)
    print("Channel Factory — YouTube force_ad_encrypted (BTS 2026)")
    print("="*65)

    # Warmup: accept YouTube/Google consent once
    ctx_yt = browser.new_context(
        viewport={"width": 1280, "height": 900},
        locale="pl-PL", user_agent=UA_D,
        ignore_https_errors=True
    )
    pg_warm = ctx_yt.new_page()
    print("\n[warmup] Accepting YouTube consent...")
    try:
        pg_warm.goto("https://www.youtube.com/", wait_until="domcontentloaded", timeout=20000)
    except: pass
    pg_warm.bring_to_front()
    time.sleep(4)
    accept_consent(pg_warm)
    time.sleep(2)
    accept_consent(pg_warm)
    time.sleep(2)
    pg_warm.close()
    print("[warmup done]")

    for fmt, pid, url in CF_ROWS:
        print(f"\n{'='*65}")
        print(f"[CF] {fmt} | pid={pid}")

        page = ctx_yt.new_page()
        flags = {"imp": False, "clk": False, "imp_url": ""}
        t_ref = [0.0]
        page.on("request", make_listener(flags, t_ref, pid, fmt))

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:
            print(f"  [load err] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(3)
        accept_consent(page)
        time.sleep(2)
        accept_consent(page)

        # Wait for ad to play and tracking to fire
        # YouTube pre-roll ads typically fire impression within first 2s of playback
        print(f"  [waiting 25s for ad to play...]")
        time.sleep(25)

        imp = flags["imp"]
        clk = flags["clk"]
        pid_c = pid in flags["imp_url"] if (pid and flags["imp_url"]) else None
        status = "PASS" if imp and clk else "IMP ONLY" if imp else "NO TAG"
        print(f"  >> {status} | pid={'OK' if pid_c else 'CHECK'}")
        results.append(("Channel Factory", fmt, pid, status, pid_c))
        page.close()

    ctx_yt.close()

    # ── Illumin (acuityplatform.com) ─────────────────────────────────────────────
    print("\n" + "="*65)
    print("Illumin — acuityplatform.com banner preview (BTS 2026)")
    print("="*65)

    for fmt, pid, url in ILLUMIN_ROWS:
        print(f"\n[Illumin] {fmt} | pid={pid}")

        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="pl-PL", user_agent=UA_D,
            ignore_https_errors=True
        )
        page = ctx.new_page()
        flags = {"imp": False, "clk": False, "imp_url": ""}
        t_ref = [0.0]
        page.on("request", make_listener(flags, t_ref, pid, fmt))

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            print(f"  [loaded]")
        except Exception as e:
            print(f"  [load err] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(12)

        imp = flags["imp"]
        clk = flags["clk"]
        pid_c = pid in flags["imp_url"] if (pid and flags["imp_url"]) else None
        status = "PASS" if imp and clk else "IMP ONLY" if imp else "NO TAG"
        print(f"  >> {status} | pid={'OK' if pid_c else 'CHECK'}")
        results.append(("Illumin", fmt, pid, status, pid_c))
        page.close()
        ctx.close()

    browser.close()

print("\n" + "="*65)
print("SUMMARY")
print("="*65)
for pub, fmt, pid, status, pid_c in results:
    print(f"  [{status:<8}] {pub} | {fmt} | pid={pid} | pid_match={'OK' if pid_c else '??'}")

log.close()
