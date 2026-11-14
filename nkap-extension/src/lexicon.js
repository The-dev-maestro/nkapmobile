/**
 * LEXIQUE VERROUILLÉ — le seul fichier qui autorise un remplacement de texte DOM.
 *
 * RÈGLES D'OR (règlement SAFINUM §9 + contrat d'intégrité) :
 * 1. Aucun nœud contenant un chiffre n'est JAMAIS modifié (`hasDigits` = garde-fou absolu :
 *    montants, frais, numéros de compte, numéros de téléphone et références restent 100 % intacts).
 * 2. L'original français est préservé dans `data-nkap-orig` → restauration instantanée ET
 *    résolution de cibles (`NKAP_QUERY`) insensible à la langue active.
 * 3. Couvre l'ensemble des libellés statiques des 5 étapes de `safinum.cm/hackathon-test`
 *    (Solde, Frais, Bénéficiaire, Récapitulatif, Confirmation + Erreurs + Sécurité).
 */

window.NKAP_LEXICON = {
  version: 2,
  entries: [
    // ── En-tête & Navigation (Stepper) ──
    { fr: "Banque en ligne", dua: "Ndabo a moni o муссо", ewo: "Nkwap", status: "validated", key: "online_bank" },
    { fr: "Solde", dua: "Moni ma dia", ewo: "Nděn", status: "demo", key: "step_balance" },
    { fr: "Frais", dua: "Mabála", ewo: "Mbug", status: "demo", key: "step_fees" },
    { fr: "Bénéficiaire", dua: "Mukusa", ewo: "Nyi á nɔŋ", status: "demo", key: "step_beneficiary" },
    { fr: "Récapitulatif", dua: "Botali", ewo: "Ntolán", status: "demo", key: "step_recap" },
    { fr: "Confirmation", dua: "Bola la mbale", ewo: "Yemban", status: "demo", key: "step_confirm" },

    // ── Écran 1 : Compte & Solde (Bloc 1 validé NSIA / Maylis) ──
    { fr: "Votre compte", dua: "Konto ango", ewo: "Nkwap woué", status: "validated", key: "your_account" },
    { fr: "Compte courant", dua: "Konto ya pondi", ewo: "Bɔ́l á mɛlú", status: "demo", key: "current_account" },
    { fr: "Solde disponible", dua: "Moni ma peńe", ewo: "Itan ineu", status: "validated", key: "balance_label" },
    { fr: "Consultez votre solde et lancez un transfert en toute sécurité.", dua: "Ombwa moni mango pe loma moni na musango.", ewo: "Bebgeu itan o beleu ou lom moany voae.", status: "validated", key: "balance_hint" },
    { fr: "Numéro de compte", dua: "Nimero a konto", ewo: "Nombo nkwap", status: "validated", key: "account_number" },
    { fr: "Effectuer un transfert", dua: "Loma moni", ewo: "Lomo moni", status: "validated", key: "do_transfer" },
    { fr: "Consulter les frais", dua: "Ombwa mabála", ewo: "Fombo itan ya yi wa tsig", status: "validated", key: "see_fees" },
    { fr: "Transactions récentes", dua: "Bebolo ba sukan", ewo: "Itang o nga kène nong itang ou dzali", status: "validated", key: "recent_tx" },
    { fr: "Dernières opérations", dua: "Bebolo ba sukan", ewo: "Itang o nga kène nong itang ou dzali", status: "validated", key: "recent_ops" },
    { fr: "Paiement marchand", dua: "Sawedi la mome-nyunga", ewo: "Maane", status: "validated", key: "tx_merchant" },
    { fr: "Salaire reçu", dua: "Musawedi mukusabe", ewo: "I maane o bi", status: "validated", key: "tx_salary" },
    { fr: "Transfert reçu", dua: "Moni malomabe", ewo: "Itan ineu nloman", status: "validated", key: "tx_transfer_in" },
    { fr: "Facture électricité", dua: "Kalati a weya", ewo: "Ayaane mfiè", status: "validated", key: "tx_electricity" },
    { fr: "Facture d'électricité", dua: "Kalati a weya", ewo: "Ayaane mfiè", status: "validated", key: "tx_electricity_alt" },

    // ── Carte latérale Sécurité (Bloc 1 validé NSIA / Maylis) ──
    { fr: "Sécurité", dua: "Musango", ewo: "Mebalan", status: "validated", key: "security_title" },
    { fr: "Vérifiez toujours le nom et le numéro du bénéficiaire avant de confirmer un transfert.", dua: "Ombwa bwam dina na nimero ya mukusa oboso ba bola loma.", ewo: "Kèguè tône fombo dzoé ai number e mod wa lom moni ossussua eneu wa lom.", status: "validated", key: "security_hint" },
    { fr: "Connexion sécurisée", dua: "Diwuta la musango", ewo: "Ewolo connexion", status: "validated", key: "secure_conn" },

    // ── Écran 2 : Frais de transfert ──
    { fr: "Frais de transfert", dua: "Mabála ma loma", ewo: "Mbug í nděn", status: "demo", key: "fees_header" },
    { fr: "Choisissez le type de transfert et le montant. Les frais sont calculés automatiquement.", dua: "Pona njika loma na муtango. Mabála mabolan muso.", ewo: "Lɔ́ mvet nděn, mbug á ɔwɔ́n lɛ́.", status: "demo", key: "transfer_hint" },
    { fr: "Type d'opération", dua: "Njika ebolo", ewo: "Mvet", status: "demo", key: "op_type" },
    { fr: "Compte Safinum", dua: "Konto Safinum", ewo: "Bɔ́l Safinum", status: "demo", key: "op_safinum" },
    { fr: "Transfert instantané et gratuit", dua: "Loma la dibokimene pe musawedi te", ewo: "Nděn nɛ́lɛ́, ɔ́ mbug lɛ́", status: "demo", key: "transfer_instant" },
    { fr: "Transfert standard", dua: "Loma la pondi", ewo: "Nděn ya mɛlú", status: "demo", key: "transfer_standard" },
    { fr: "Transfert express", dua: "Loma la ponda", ewo: "Nděn avól", status: "demo", key: "transfer_express" },
    { fr: "Montant à envoyer", dua: "Moni ma loma", ewo: "Nděn tó", status: "demo", key: "amount_to_send" },
    { fr: "Gratuit", dua: "Bonam", ewo: "Zɛ́zɛ", status: "demo", key: "free_badge" },
    { fr: "Total à débiter", dua: "Botali ba busa", ewo: "Ntolán wɔ́g", status: "demo", key: "total_to_debit" },
    { fr: "Solde après opération", dua: "Moni ma dia ombusa", ewo: "Nděn wɔ́g í bɔ́l á mvet", status: "demo", key: "balance_after" },
    { fr: "Retour", dua: "Timba", ewo: "Bulan", status: "demo", key: "btn_back" },
    { fr: "Continuer", dua: "Ala oboso", ewo: "Kɛlɛ́ obúsú", status: "demo", key: "btn_continue" },

    // ── Écran 3 : Bénéficiaire ──
    { fr: "Renseignez les informations du destinataire. Vérifiez toujours le numéro avant de valider.", dua: "Tila myango ma mukusa. Ombwa nimero oboso ba bola.", ewo: "Bɔ́l nem á lɔ́n, ɛlɛ́ɛ́ kɛ́.", status: "demo", key: "recipient_hint" },
    { fr: "Ce bénéficiaire n'a jamais été utilisé sur ce compte. Vérifiez le numéro avant de continuer.", dua: "Nu mukusa a si bolane o konto. Ombwa nimero oboso ba ala.", ewo: "Nyi nyɔ́ a ngenan tekeulan. Fombɔ́k nɔ́mbɔ.", status: "demo", key: "new_benef_warn" },
    { fr: "Nom du bénéficiaire", dua: "Dina la mukusa", ewo: "Nem á nyi", status: "demo", key: "benef_name" },
    { fr: "Numéro de téléphone", dua: "Nimero a telefone", ewo: "Nem tɛlɛfɔ́n", status: "demo", key: "benef_phone" },
    { fr: "Motif du transfert", dua: "Njom a loma", ewo: "Sɔ́n nděn", status: "demo", key: "transfer_reason" },
    { fr: "Note (optionnel)", dua: "Mwendi (o tondi te)", ewo: "Efíá", status: "demo", key: "note_opt" },
    { fr: "J'ai vérifié le nom et le numéro du bénéficiaire.", dua: "Na ombwe dina na nimero ya mukusa.", ewo: "Nɛ́lɛ nem á nyi.", status: "demo", key: "benef_checked" },

    // ── Écran 4 : Récapitulatif ──
    { fr: "Vérifiez les informations avant de confirmer le transfert.", dua: "Ombwa myango mese oboso ba bola loma.", ewo: "Ɛlɛ́ɛ́ kɛ́, zɔ́ bɔ́l.", status: "demo", key: "verify_hint" },
    { fr: "Montant", dua: "Moni", ewo: "Nděn", status: "demo", key: "label_amount" },
    { fr: "Total débité", dua: "Botali busabe", ewo: "Ntolán", status: "demo", key: "label_total_debited" },
    { fr: "Téléphone", dua: "Telefone", ewo: "Tɛlɛfɔ́n", status: "demo", key: "label_phone" },
    { fr: "Référence", dua: "Edun", ewo: "Nɔ́mbɔ ndem", status: "demo", key: "label_ref" },
    { fr: "Opération", dua: "Ebolo", ewo: "Mvet", status: "demo", key: "label_op" },
    { fr: "Motif", dua: "Njom", ewo: "Sɔ́n", status: "demo", key: "label_reason" },
    { fr: "Je confirme que les informations ci-dessus sont correctes.", dua: "Na bamse na myango ma tenge.", ewo: "Me yemban ná mam mese me ne mbɛn.", status: "demo", key: "confirm_checkbox" },
    { fr: "Modifier", dua: "Tukwa", ewo: "Tyendé", status: "demo", key: "btn_edit" },
    { fr: "Confirmer le transfert", dua: "Bamse loma", ewo: "Yemban nděn", status: "demo", key: "btn_confirm_transfer" },

    // ── Écran 5 : Reçu / Confirmation ──
    { fr: "Transfert confirmé", dua: "Loma dibamsebe", ewo: "Nděn é kɛ́ya", status: "demo", key: "receipt_title" },
    { fr: "Votre opération a été enregistrée avec succès.", dua: "Ebolo ango e tilabe na bwam.", ewo: "Mvet wɔ́g ó tiliban mbɛn.", status: "demo", key: "receipt_sub" },
    { fr: "Nouveau solde disponible", dua: "Moni ma peńe ma dia", ewo: "Nděn mfefé í bɔ́l", status: "demo", key: "receipt_new_balance" },
    { fr: "Nouveau transfert", dua: "Loma dipepe", ewo: "Nděn mfefé", status: "demo", key: "btn_new_transfer" },
    { fr: "Retour à l'accueil", dua: "Timba o bekombo", ewo: "Bulan á ndá", status: "demo", key: "btn_back_home" },

    // ── Bannières d'erreurs & Contenu inédit (P5 / Jury) ──
    { fr: "Une erreur est survenue", dua: "Njom e bodi", ewo: "Ékop é kuiya", status: "demo", key: "err_header" },
    { fr: "Solde insuffisant pour effectuer ce transfert.", dua: "Moni ma si kolisane o bola loma.", ewo: "Nděn ɔ́g bɔ́l, ɔ́ sɔ́k lɛ́.", status: "demo", key: "err_balance" },
    { fr: "Solde insuffisant", dua: "Moni ma si kolisane", ewo: "Nděn ɔ́g bɔ́l", status: "demo", key: "err_balance_short" },
    { fr: "Alerte de sécurité", dua: "Bediedi ba musango", ewo: "Měbɛndé m'ékálí", status: "demo", key: "alert_header" },
    { fr: "Alerte de sécurité : vérifiez le numéro du bénéficiaire avant de continuer.", dua: "Bediedi ba musango : ombwa nimero ya mukusa oboso ba ala.", ewo: "Ɛlɛ́ɛ́ nem tɛlɛfɔ́n, ɔ́ bɔ́l.", status: "demo", key: "alert_phone" },
    { fr: "Vérifiez le numéro du bénéficiaire avant de continuer.", dua: "Ombwa nimero ya mukusa oboso ba ala.", ewo: "Bɛ́gɛ̌ nem tɛlɛfɔ́n mɔt ô bɛsú.", status: "demo", key: "alert_phone_body" },
    { fr: "Ne partagez jamais votre code secret. Un agent ne vous le demandera pas.", dua: "O si langwea moto kode ango ya dimbambe.", ewo: "Te ve mɔt kode wɔ́g ya nsolán.", status: "demo", key: "err_pin_warn" },
    { fr: "Erreur réseau", dua: "Njom a singi", ewo: "Ɛ́vúdú á nsíŋgi", status: "demo", key: "err_network_short" },
    { fr: "Erreur réseau : le service est temporairement indisponible. Réessayez.", dua: "Njom a singi : kekise peńe.", ewo: "Ɛ́vúdú á nsíŋgi. Lɔ́ kɔ́.", status: "demo", key: "err_network" },
    { fr: "Le service est temporairement indisponible. Réessayez.", dua: "Ebolo e si ma-babe tatan. Kekise peńe.", ewo: "Isáɛ é sě bɛ́n. Lɔ́ kɔ́.", status: "demo", key: "err_network_body" },
    { fr: "Message important", dua: "Mwendi ma mweńa", ewo: "Efíá é ne mfi", status: "demo", key: "unseen_header" },
  ],

  /** true si l'entrée peut remplacer le texte affiché. */
  isUsable: (e) => e.status === "validated" || e.status === "demo",

  /** Garde-fou intégrité : un texte contenant un chiffre n'est jamais remplacé. */
  hasDigits: (s) => /\d/.test(s),

  /** Trouve l'entrée correspondant EXACTEMENT au texte d'un nœud. */
  exactMatch: function (text) {
    const t = text.replace(/\s+/g, " ").trim();
    if (!t || this.hasDigits(t)) return null; // garde-fou montants
    const lower = t.toLowerCase();
    return (
      this.entries.find(
        (e) => this.isUsable(e) && e.fr.toLowerCase() === lower
      ) || null
    );
  },
};
