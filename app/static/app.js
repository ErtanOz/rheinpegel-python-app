(() => {
    const script = document.currentScript;
    if (!script) {
        return;
    }

    const apiLatest = script.dataset.apiLatest;
    const refreshSeconds = Number.parseInt(script.dataset.refresh ?? "120", 10) || 120;
    const demoFlag = script.dataset.demo === "true";
    const timezone = document.body?.dataset?.timezone || "Europe/Berlin";

    const levelValue = document.getElementById("levelValue");
    const warningBadge = document.getElementById("warningBadge");
    const trendBadge = document.getElementById("trendBadge");
    const trendSymbol = document.getElementById("trendSymbol");
    const updatedTime = document.getElementById("updatedTime");
    const relativeAge = document.getElementById("relativeAge");
    const countdown = document.getElementById("countdown");
    const refreshButton = document.getElementById("refreshButton");
    const autoToggle = document.getElementById("autoRefreshToggle");
    const sparklinePath = document.getElementById("sparklinePath");
    const errorBanner = document.getElementById("errorBanner");
    const demoBadge = document.getElementById("demoBadge");

    const initialDataEl = document.getElementById("initial-data");
    let initialPayload = { latest: null, history: [], autoRefresh: refreshSeconds, demo: demoFlag };
    if (initialDataEl?.textContent) {
        try {
            initialPayload = JSON.parse(initialDataEl.textContent);
        } catch (err) {
            console.warn("Failed to parse initial payload", err);
        }
    }

    const state = {
        autoRefresh: true,
        secondsRemaining: refreshSeconds,
        lastMeasurement: initialPayload.latest ?? null,
        history: initialPayload.history ?? [],
        demoMode: demoFlag || Boolean(initialPayload.demo),
        timezone,
    };

    const dateFormatter = new Intl.DateTimeFormat("de-DE", {
        timeZone: timezone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    });

    function showError(message) {
        if (!errorBanner) return;
        errorBanner.textContent = message;
        errorBanner.hidden = false;
    }

    function clearError() {
        if (!errorBanner) return;
        errorBanner.textContent = "";
        errorBanner.hidden = true;
    }

    function warningFor(level) {
        if (level < 400) {
            return { label: "Normal", cls: "badge-normal" };
        }
        if (level < 600) {
            return { label: "Aufmerksamkeit", cls: "badge-attention" };
        }
        if (level < 800) {
            return { label: "Warnung", cls: "badge-warning" };
        }
        return { label: "Alarm", cls: "badge-alarm" };
    }

    function trendInfo(trendValue) {
        switch (trendValue) {
            case 1:
                return { label: "steigend", symbol: "↑", cls: "badge-rising" };
            case -1:
                return { label: "fallend", symbol: "↓", cls: "badge-falling" };
            default:
                return { label: "gleichbleibend", symbol: "→", cls: "badge-stable" };
        }
    }

    function computeSparkline(history) {
        if (!history || history.length === 0) {
            return "";
        }
        const levels = history.map((entry) => Number(entry.level_cm ?? entry.levelCm)).filter((v) => Number.isFinite(v));
        if (levels.length === 0) {
            return "";
        }
        const min = Math.min(...levels);
        const max = Math.max(...levels);
        const span = Math.max(max - min, 1);
        const step = 100 / Math.max(levels.length - 1, 1);
        const parts = levels.map((level, index) => {
            const x = index * step;
            const y = 40 - ((level - min) / span) * 40;
            return `${x.toFixed(2)},${y.toFixed(2)}`;
        });
        return `M ${parts.join(" L ")}`;
    }

    function updateDemoBadge(isDemo) {
        if (!demoBadge) return;
        if (isDemo) {
            demoBadge.hidden = false;
            document.body?.setAttribute("data-demo", "true");
        } else {
            demoBadge.hidden = true;
            document.body?.setAttribute("data-demo", "false");
        }
    }

    function updateUI(measurement, history) {
        if (!measurement) {
            showError("Keine Messdaten verfügbar");
            return;
        }
        state.lastMeasurement = measurement;
        state.history = history ?? state.history;
        clearError();

        if (levelValue) {
            levelValue.textContent = measurement.level_cm ?? measurement.levelCm;
        }
        const warning = warningFor(measurement.level_cm ?? measurement.levelCm);
        if (warningBadge) {
            warningBadge.className = `badge ${warning.cls}`;
            warningBadge.textContent = warning.label;
        }
        const trend = trendInfo(measurement.trend);
        if (trendBadge) {
            trendBadge.className = `badge trend-badge ${trend.cls}`;
            trendBadge.setAttribute("aria-label", `Trend ${trend.label}`);
        }
        if (trendSymbol) {
            trendSymbol.textContent = trend.symbol;
        }
        if (updatedTime) {
            updatedTime.dataset.timestamp = measurement.timestamp;
            const date = new Date(measurement.timestamp);
            updatedTime.textContent = `Zuletzt aktualisiert: ${dateFormatter.format(date)} Uhr`;
        }
        updateRelativeAge();
        updateDemoBadge(Boolean(measurement.is_demo ?? measurement.isDemo));

        if (sparklinePath) {
            sparklinePath.setAttribute("d", computeSparkline(state.history.slice(-24)));
        }
    }

    function updateRelativeAge() {
        if (!relativeAge || !state.lastMeasurement?.timestamp) {
            return;
        }
        const lastDate = new Date(state.lastMeasurement.timestamp);
        const diffSeconds = Math.max(0, Math.floor((Date.now() - lastDate.getTime()) / 1000));
        if (diffSeconds < 5) {
            relativeAge.textContent = "vor wenigen Sekunden";
            return;
        }
        if (diffSeconds < 60) {
            relativeAge.textContent = `vor ${diffSeconds} Sekunden`;
            return;
        }
        const minutes = Math.floor(diffSeconds / 60);
        const seconds = diffSeconds % 60;
        relativeAge.textContent = `vor ${minutes} Minute${minutes === 1 ? "" : "n"} und ${seconds} Sekunde${seconds === 1 ? "" : "n"}`;
    }

    function updateCountdown() {
        if (!countdown) return;
        if (!state.autoRefresh) {
            countdown.textContent = "Auto-Refresh deaktiviert";
            return;
        }
        const minutes = Math.floor(state.secondsRemaining / 60);
        const seconds = state.secondsRemaining % 60;
        countdown.textContent = `Nächste Aktualisierung in ${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }

    async function refreshNow() {
        if (!apiLatest) return;
        if (refreshButton) {
            refreshButton.disabled = true;
        }
        try {
            const url = new URL(apiLatest, window.location.origin);
            if (state.demoMode) {
                url.searchParams.set("demo", "1");
            }
            const response = await fetch(url.toString(), { headers: { Accept: "application/json" } });
            if (!response.ok) {
                throw new Error(`Serverfehler ${response.status}`);
            }
            const payload = await response.json();
            if (payload.error) {
                showError(payload.error);
            } else {
                clearError();
            }
            state.demoMode = Boolean(payload.demo_mode ?? payload.demoMode ?? state.demoMode);
            updateUI(payload.measurement, payload.history);
            state.secondsRemaining = refreshSeconds;
            updateCountdown();
        } catch (error) {
            console.error("Aktualisierung fehlgeschlagen", error);
            showError("Aktualisierung fehlgeschlagen. Bitte später erneut versuchen.");
        } finally {
            if (refreshButton) {
                refreshButton.disabled = false;
            }
        }
    }

    if (autoToggle) {
        autoToggle.addEventListener("change", (event) => {
            state.autoRefresh = event.target.checked;
            autoToggle.setAttribute("aria-checked", state.autoRefresh ? "true" : "false");
            if (state.autoRefresh) {
                state.secondsRemaining = refreshSeconds;
            }
            updateCountdown();
        });
    }

    if (refreshButton) {
        refreshButton.addEventListener("click", () => {
            refreshNow();
        });
    }

    setInterval(() => {
        if (!state.autoRefresh) {
            return;
        }
        state.secondsRemaining -= 1;
        if (state.secondsRemaining <= 0) {
            state.secondsRemaining = refreshSeconds;
            refreshNow();
        }
        updateCountdown();
    }, 1000);

    setInterval(updateRelativeAge, 1000);

    updateUI(state.lastMeasurement, state.history);
    updateCountdown();
})();
