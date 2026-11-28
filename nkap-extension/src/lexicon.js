/**
 * LEXIQUE VERROUILLÉ — le seul fichier qui autorise un remplacement de texte DOM.
 *
 * RÈGLES D'OR (règlement SAFINUM §9 + contrat d'intégrité) :
 * 1. Aucun nœud contenant un chiffre n'est JAMAIS modifié (`hasDigits` = garde-fou absolu :
 *    montants, frais, numéros de compte, numéros de téléphone et références restent 100 % intacts).
 * 2. L'original (français ou anglais) est préservé dans `data-nkap-orig` → restauration instantanée ET
 *    résolution de cibles (`NKAP_QUERY`) insensible à la langue active.
 * 3. ZÉRO placeholder non validé : seules les entrées `status: "validated"` issues des corpus humains
 *    (lexique manuscrit Duálá + dataset natif Duálá + dataset natif Ewondo Nsia) sont autorisées.
 *    Tout libellé non validé reste intact dans sa langue d'origine.
 */

window.NKAP_LEXICON = {
  version: 4,
  entries: [
    // ── En-tête & Navigation (Stepper) ──
    { fr: "Banque en ligne", en: "Online banking", dua: "Banki o internet", ewo: null, status: "validated", key: "online_bank" },
    { fr: "Solde", en: "Balance", dua: "Edia", ewo: null, status: "validated", key: "step_balance" },
    { fr: "Frais", en: ["Fees", "Fee"], dua: "Mususedi", ewo: "Be frais", status: "validated", key: "step_fees" },
    { fr: "Bénéficiaire", en: "Beneficiary", dua: "Mukusedi", ewo: "Za yaa a di", status: "validated", key: "step_beneficiary" },
    { fr: "Récapitulatif", en: "Summary", dua: "Kotele", ewo: null, status: "validated", key: "step_recap" },
    { fr: "Confirmation", en: "Confirmation", dua: "Bamse", ewo: null, status: "validated", key: "step_confirm" },

    // ── Écran 1 : Compte & Solde ──
    { fr: "Votre compte", en: "Your account", dua: "ekotèlè", ewo: "Nkwap woué", status: "validated", key: "your_account" },
    { fr: "Bonjour, Amina", en: "Hello, Amina", dua: "Idiba bwam, Amina", ewo: "Mbə̀mbə́ kídí, Amina", status: "validated", key: "hello_amina" },
    { fr: "Bonjour", en: "Hello", dua: "Idiba bwam", ewo: "Mbə̀mbə́ kídí", status: "validated", key: "hello" },
    { fr: "Compte courant", en: "Current account", dua: "Kalata konti", ewo: null, status: "validated", key: "current_account" },
    { fr: "Solde disponible", en: "Available balance", dua: "Moni mu diya", ewo: "Itan ineu a nkwap", status: "validated", key: "balance_label" },
    { fr: "Consultez votre solde et lancez un transfert en toute sécurité.", en: "Check your balance and start a secure transfer.", dua: "Ombwa moni mu diya, na o lome na musango.", ewo: "Bebgeu itan o beleu ou lom moany voae.", status: "validated", key: "balance_hint" },
    { fr: "Numéro de compte", en: "Account number", dua: "Number benengedi ba mbolo", ewo: null, status: "validated", key: "account_number" },
    { fr: "Effectuer un transfert", en: "Make a transfer", dua: "Tombise mbolo", ewo: "Lomo moni", status: "validated", key: "do_transfer" },
    { fr: "Consulter les frais", en: "View fees", dua: "Jombwa mbolo", ewo: "Fombo itan ya yi wa tsig", status: "validated", key: "see_fees" },
    { fr: "Transactions récentes", en: "Recent transactions", dua: "Misongi Misukan", ewo: "Itang o nga kène nong itang ou dzali", status: "validated", key: "recent_tx" },
    { fr: "Dernières opérations", dua: "Bebolo ba sukan", ewo: "Itang o nga kène nong itang ou dzali", status: "validated", key: "recent_ops" },
    { fr: "Paiement marchand", en: "Merchant payment", dua: "Musawedi ma nyunga", ewo: null, status: "validated", key: "tx_merchant" },
    { fr: "Salaire reçu", en: "Salary received", dua: "Kusa la musawedi", ewo: null, status: "validated", key: "tx_salary" },
    { fr: "Transfert reçu", en: "Transfer received", dua: "Kusa la betombedi", ewo: null, status: "validated", key: "tx_transfer_in" },
    { fr: ["Facture électricité", "Facture d'électricité"], en: "Electricity bill", dua: "Dipapa la beturkan", ewo: null, status: "validated", key: "tx_electricity" },
    { fr: "Facture d'eau", en: "Water bill", dua: "Dipapa la madiba", ewo: null, status: "validated", key: "tx_water" },
    { fr: "Recharge téléphone", en: "Phone top-up", dua: "Londe la beboledi", ewo: "Wa couss ikola", status: "validated", key: "tx_airtime" },
    { fr: "Retrait", en: "Withdrawal", dua: "Sumua", ewo: null, status: "validated", key: "tx_withdrawal" },
    { fr: "Dépôt", en: "Deposit", dua: "Wele", ewo: null, status: "validated", key: "tx_deposit" },
    { fr: "Remboursement", en: "Refund", dua: "Timbisele", ewo: null, status: "validated", key: "tx_refund" },
    { fr: "Abonnement", en: "Subscription", dua: "Tidise", ewo: null, status: "validated", key: "tx_subscription" },

    // ── Carte latérale Sécurité ──
    { fr: "Sécurité", en: "Security", dua: "Musango", ewo: null, status: "validated", key: "security_title" },
    { fr: "Vérifiez toujours le nom et le numéro du bénéficiaire avant de confirmer un transfert.", en: "Always verify the beneficiary name and number before confirming a transfer.", dua: "Jombwa la dina na number mutombwedi.", ewo: "Kèguè tône fombo dzoé ai number e mod wa lom moni ossussua eneu wa lom.", status: "validated", key: "security_hint" },
    { fr: "Connexion sécurisée", en: "Secure connection", dua: "Ingueya na musango", ewo: "Ewolo connexion", status: "validated", key: "secure_conn" },

    // ── Écran 2 : Frais de transfert ──
    { fr: "Frais de transfert", en: "Transfer fees", dua: "Mususedi mwa betombedi", ewo: null, status: "validated", key: "fees_header" },
    { fr: "Choisissez le type de transfert et le montant. Les frais sont calculés automatiquement.", en: "Choose the transfer type and amount. Fees are calculated automatically.", dua: "Poso mwaninga o maloma no, Musongi mwèsè mu ma busa.", ewo: null, status: "validated", key: "transfer_hint" },
    { fr: "Type d'opération", en: "Operation type", dua: "Loma", ewo: null, status: "validated", key: "op_type" },
    { fr: "Compte Safinum", en: "Safinum account", dua: "Kont a safinum", ewo: null, status: "validated", key: "op_safinum" },
    { fr: "Autre banque", en: "Other bank", dua: "Bank ni pè pè", ewo: null, status: "validated", key: "op_other_bank" },
    { fr: "Transfert instantané et gratuit", en: "Instant, free transfer", dua: "Loma tatan e si bè sawa", ewo: null, status: "validated", key: "transfer_instant" },
    { fr: "Montant à envoyer", en: "Amount to send", dua: "Moni o maloma no", ewo: null, status: "validated", key: "amount_to_send" },
    { fr: "Gratuit", en: "Free", dua: "Mususedi to mô", ewo: null, status: "validated", key: "free_badge" },
    { fr: "Total à débiter", en: "Total to debit", dua: "Nje yese bangamene no o sumua", ewo: "Itang i tzigban", status: "validated", key: "total_to_debit" },
    { fr: "Solde après opération", en: "Balance after transfer", dua: "Ndje e peti", ewo: "Itang i ligui", status: "validated", key: "balance_after" },
    { fr: "Retour", en: "Back", dua: "Timba", ewo: "Dougan ai mvous", status: "validated", key: "btn_back" },
    { fr: "Continuer", en: "Continue", dua: "Wa la ne", ewo: "Keleu ossou", status: "validated", key: "btn_continue" },

    // ── Écran 3 : Bénéficiaire ──
    { fr: "Renseignez les informations du destinataire. Vérifiez toujours le numéro avant de valider.", en: "Enter the recipient details. Always verify the number before confirming.", dua: "Tila mambo ma mukasedi. Ombwa numb ao bwam o boso na o maloma.", ewo: null, status: "validated", key: "recipient_hint" },
    { fr: "Ce bénéficiaire n'a jamais été utilisé sur ce compte. Vérifiez le numéro avant de continuer.", en: "This beneficiary has never been used on this account. Verify the number before continuing.", dua: "Nu mukasedi a titi o kalata konti. Ombwa bwam o bia na o mala o boso.", ewo: null, status: "validated", key: "new_benef_warn" },
    { fr: "Nom du bénéficiaire", en: "Beneficiary name", dua: "Dina la mutombwedi", ewo: null, status: "validated", key: "benef_name" },
    { fr: "Numéro de téléphone", en: "Phone number", dua: "Number ebelane", ewo: null, status: "validated", key: "benef_phone" },
    { fr: "Motif du transfert", en: "Transfer reason", dua: "Nyoma betombedi", ewo: null, status: "validated", key: "transfer_reason" },
    { fr: "J'ai vérifié le nom et le numéro du bénéficiaire.", en: "I have verified the beneficiary name and phone number.", dua: "Nombo dina na number mukasedi.", ewo: null, status: "validated", key: "benef_checked" },

    // ── Écran 4 : Récapitulatif ──
    { fr: "Vérifiez les informations avant de confirmer le transfert.", en: "Check the details before confirming the transfer.", dua: "Sele jombwa miango mese to denga wa bamse.", ewo: null, status: "validated", key: "verify_hint" },
    { fr: "Montant", en: "Amount", dua: "Musongi", ewo: "Tang moni", status: "validated", key: "label_amount" },
    { fr: "Total débité", en: "Total debited", dua: "Musongi mu londi", ewo: "Itang i tzigban", status: "validated", key: "label_total_debited" },
    { fr: "Téléphone", en: "Phone", dua: "Number ebelane", ewo: null, status: "validated", key: "label_phone" },
    { fr: "Référence", en: "Reference", dua: "Epasi", ewo: null, status: "validated", key: "label_ref" },
    { fr: "Opération", en: "Operation", dua: "Ebolo", ewo: null, status: "validated", key: "label_op" },
    { fr: "Motif", dua: "Nyoma", ewo: null, status: "validated", key: "label_reason" },
    { fr: "Je confirme que les informations ci-dessus sont correctes.", en: "I confirm the information above is correct.", dua: "Matila ma tenguènè.", ewo: null, status: "validated", key: "confirm_checkbox" },
    { fr: "Modifier", en: "Edit", dua: "Tukwa", ewo: "Tsenegué numba ngueu tang", status: "validated", key: "btn_edit" },
    { fr: "Confirmer le transfert", en: "Confirm transfer", dua: "Bamsè loma moni", ewo: "Yi wa yebeu", status: "validated", key: "btn_confirm_transfer" },
    { fr: "Annuler", en: "Cancel", dua: "Sumua", ewo: "Dîmi", status: "validated", key: "btn_cancel" },
    { fr: "Réessayer", en: "Try again", dua: "Kekise pete", ewo: null, status: "validated", key: "btn_retry" },
    { fr: "Télécharger le reçu", en: "Download receipt", dua: "Sane la dipapa", ewo: null, status: "validated", key: "btn_download_receipt" },
    { fr: "Aide", en: "Help", dua: "Jongwane", ewo: null, status: "validated", key: "btn_help" },

    // ── Écran 5 : Reçu / Confirmation ──
    { fr: ["Transfert effectué", "Transfert confirmé"], en: "Transfer completed", dua: "Ebolanè", ewo: null, status: "validated", key: "receipt_title" },
    { fr: ["Votre transfert a été envoyé avec succès.", "Votre opération a été enregistrée avec succès."], en: "Your transfer has been sent successfully.", dua: "Moni mu busi mbwam.", ewo: null, status: "validated", key: "receipt_sub" },
    { fr: "Nouveau transfert", en: "New transfer", dua: "Loma la pena", ewo: null, status: "validated", key: "btn_new_transfer" },

    // ── Contenu dynamique validé ──
    { fr: "Message important", en: "Important message", dua: "Mwendi mwa muegna", ewo: null, status: "validated", key: "unseen_header" },
  ],

  /** true uniquement si l'entrée est validée par un locuteur humain (zéro placeholder demo). */
  isUsable: (e) => e.status === "validated",

  /** Garde-fou intégrité : un texte contenant un chiffre n'est jamais remplacé. */
  hasDigits: (s) => /\d/.test(s),

  /** Tous les libellés source (FR + EN) d'une entrée. */
  sourceForms: function (entry) {
    const out = [];
    const push = (v) => {
      if (Array.isArray(v)) v.forEach((x) => x && out.push(x));
      else if (v) out.push(v);
    };
    push(entry.fr);
    push(entry.en);
    return out;
  },

  /** Forme française canonique d'une entrée. */
  canonicalFr: (entry) => (Array.isArray(entry.fr) ? entry.fr[0] : entry.fr) || "",

  /** Trouve l'entrée correspondant EXACTEMENT au texte d'un nœud (FR ou EN). */
  exactMatch: function (text) {
    const t = text.replace(/\s+/g, " ").trim();
    if (!t || this.hasDigits(t)) return null; // garde-fou montants
    const lower = t.toLowerCase();
    return (
      this.entries.find(
        (e) =>
          this.isUsable(e) &&
          this.sourceForms(e).some((f) => f.toLowerCase() === lower)
      ) || null
    );
  },
};
