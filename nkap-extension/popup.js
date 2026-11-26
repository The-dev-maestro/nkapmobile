const ewondo = document.getElementById("ewondoOn");
const brain = document.getElementById("brainUrl");
const save = document.getElementById("save");

chrome.storage.sync.get({ ewondoOn: false, brainUrl: "https://13.51.168.107.sslip.io" }, (cfg) => {
  ewondo.checked = cfg.ewondoOn;
  brain.value = cfg.brainUrl || "https://13.51.168.107.sslip.io";
});

save.addEventListener("click", () => {
  chrome.storage.sync.set({ ewondoOn: ewondo.checked, brainUrl: brain.value.trim() }, () => {
    // propager aux onglets actifs
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) chrome.tabs.sendMessage(tabs[0].id, { type: "settings", ewondoOn: ewondo.checked, brainUrl: brain.value.trim() }).catch(() => {});
    });
    save.textContent = "Enregistré ✓";
    setTimeout(() => (save.textContent = "Enregistrer"), 1200);
  });
});
