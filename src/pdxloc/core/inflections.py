"""Функции склонения, которыми переводы Paradox чинят русскую грамматику.

Списки — **данные, снятые с живых деревьев**, а не догадка. В обе игры они
попали одинаково: взяты вызовы, которые встречаются в русском дереве и **ни
разу** в английском. Отсюда и надёжность отбора: опечатка переводчика
(`[BRA.GetADjectiveCap]`, `[FROM.GetAdejctive]` — обе живые) в английском тоже
не встречается, но в русском попадается раз-другой, а настоящая функция —
сотнями. Поэтому у CK2, где таких вызовов много, взят ещё и порог по частоте.

Зачем это правилам. Английское `[JAP.GetAdjective]` переводчик заменяет на
`[JAP.GetAdjRuLower]` и дописывает окончание, а `[X.GetName]` превращает в
«сража[X.GetLasLsya], [X.GetFirstName]». Проверка «набор ссылок должен
совпадать» видит здесь потерю и добавление — то есть ошибку, — хотя перед нами
приём самой игры. Списки гасят ровно этот случай: см. параметр
`ignore_extra_tails` у правила `brackets_mismatch` и `ending_calls` у
`glued_markup` в `core/qa_rules.py`.
"""
from __future__ import annotations

# --- Hearts of Iron IV -----------------------------------------------------
#
# 33 функции, покрывают 5 918 добавленных вызовов ванильного русского перевода.
HOI4_RU_CALLS = [
    "GetAdjRuEnd", "GetAdjRuLower", "GetAdjectiveRuLower",
    "GetEgoEye_RU", "GetEmuEy_RU",
    "GetNameEndRuPresentEtUt", "GetNameEndRuPresentEtYut",
    "GetNameInst", "GetNameRuAcc", "GetNameRuDat", "GetNameRuEndPast",
    "GetNameRuGen", "GetNameRuInst", "GetNameRuPrep", "GetNameSuffixRuDzhetGut",
    "GetOnOna_RU", "GetOnOna_RUCap",
    "GetRajNameDat", "GetRajNameRUGen", "GetRajNameRuAcc", "GetRajNameRuDat",
    "GetRajNameRuGen", "GetRajNameRuPrep",
    "GetRulingIdeologyNoun_RU_lower_Acc", "GetRulingIdeologyNoun_RU_lower_Gen",
    "GetRulingIdeologyNoun_RU_lower_Nom",
    "GetRulingIdeology_RU_Adj_Ending_IeYe", "GetRulingIdeology_RU_Adj_Ending_IhYh",
    "GetRulingIdeology_RU_lower_Adherent_Nom", "GetRulingIdeology_RU_lower_ShortAdj",
    "GetRussiansDemonym_RU_Inst", "GetSovietArmyBasedOnIdeology_RU_END_NOM",
    "GetVerbGendEndA_RU",
]

# Те из них, что возвращают не слово, а его окончание: к ним текст дописывают
# вплотную — «объявил[CHI.GetVerbGendEndA_RU]», — и пробела там быть не должно.
HOI4_RU_ENDINGS = [c for c in HOI4_RU_CALLS
                   if "End" in c or "Ending" in c or "Suffix" in c or "END" in c]

# --- Crusader Kings II -----------------------------------------------------
#
# Здесь приём тот же, но размах другой: русская CK2 склоняет всё подряд, и
# таких вызовов набирается 881 на 25 786 вхождений. В список берём встреченные
# пять раз и чаще — 259 функций и 95,7 % вхождений. Хвост из одиночек отброшен
# намеренно: там и живут опечатки (`GeAdjective`, `GerHerHim`, `EndA` без
# `Get`), а прощать их нельзя — такой вызов в игре не сработает.
#
# Отдельного списка окончаний нет: в CK2 к слову вплотную дописывают почти
# любую из этих функций, поэтому `glued_markup` получает тот же набор.
CK2_RU_CALLS = [
    "GetAbsPossPronoun", "GetAdultererAdulteressLong", "GetAgedPerson",
    "GetAgedPersonACC", "GetAgedPersonC", "GetAgedPersonDAT",
    "GetAgedPersonGEN", "GetAgedPersonINS", "GetAgedPersonM",
    "GetAgedPersonMACC", "GetAgedPersonPREP", "GetAlcoholGEN",
    "GetArtifactSourceGEN", "GetAssasinsGreeting", "GetAssasinsHGod",
    "GetAustriaNameGEN", "GetAuthorLabel", "GetAuthorNameGEN",
    "GetAuthorTitleGEN", "GetAyaIy", "GetAyaOy", "GetAyaYy",
    "GetBaptismPostfixAndName", "GetBodyPartInjuredACC",
    "GetBookThemeACC", "GetBuilding", "GetBuildingPREP",
    "GetCapitalBuilding", "GetCapitalBuildingGEN",
    "GetCapitalBuildingPREP", "GetCapitalHoldingGEN", "GetCatholicAdj",
    "GetChamberACC", "GetChamberPREP", "GetChineseComplimentAdjectiveCap",
    "GetChkaK", "GetChristNameGEN", "GetCultureAdj",
    "GetCulturePluralGEN", "GetDWDevilDAT", "GetDWDevilGEN",
    "GetDaughterSonCap", "GetDeathReaper", "GetDeathReaperShort",
    "GetDecidedWeaponEndA", "GetDecidedWeaponUyuYy", "GetDiseasePREP",
    "GetDislikeACC", "GetEmpressEmperor", "GetEmpressEmperorCapDAT",
    "GetEmpressEmperorCapGEN", "GetEmpressEmperorCapINS", "GetEndA",
    "GetEndAOpp", "GetEndIha", "GetEndItsa", "GetEndKa", "GetEndNa",
    "GetEndNitsa", "GetEndSha", "GetEtaEtot", "GetEyEm", "GetEyIm",
    "GetEyImOpp", "GetEyYom", "GetEyuIm", "GetFertilityGoddessACC",
    "GetFertilityGoddessDAT", "GetFriendMF", "GetFromEndEA",
    "GetFromFromVsRelation", "GetFromVsRelation", "GetGlaYog",
    "GetGroundDescPREP", "GetHGodEndA", "GetHOWOyOgo", "GetHaruspexEndA",
    "GetHaruspexEndNitsa", "GetHaruspexLasLsya", "GetHaruspexSheHe",
    "GetHaruspexSoftNitseyEm", "GetHerHimCap",
    "GetHermeticsDestinedExpertiseINS",
    "GetHermeticsDestinedRoleWithAdjINS", "GetHersHisCap",
    "GetHersHisOpp", "GetHoldingGenericPlace",
    "GetHoldingGenericPlaceGEN", "GetHoldingPlace", "GetHonorificDAT",
    "GetHouseOfWorshipACC", "GetHouseOfWorshipAdjCap",
    "GetHouseOfWorshipGEN", "GetHouseOfWorshipPREP", "GetHousePREP",
    "GetHusbandWifeACC", "GetHusbandWifeDAT", "GetHusbandWifeGEN",
    "GetHusbandWifeINS", "GetHusbandWifeOppACC", "GetHusbandWifeOppGEN",
    "GetHusbandWifeOppINS", "GetIngredientLabel", "GetItsaEts",
    "GetJewsNameGENACC", "GetKaEts", "GetKiA", "GetKoyOm", "GetKuA",
    "GetLaYol", "GetLadLassINS", "GetLangAdjective", "GetLasLsya",
    "GetLasSya", "GetLikeACC", "GetLocMyChamberACC",
    "GetLocMyChamberPREP", "GetLocYourChamberACC", "GetLordLadyACC",
    "GetLordLadyCap", "GetLordLadyDAT", "GetLordLadyGEN",
    "GetLordLadyINS", "GetMOCodeDAT", "GetMOSaintGEN", "GetMarried",
    "GetMarryZaNa", "GetMomDad", "GetMomDadCap", "GetMotherFatherGEN",
    "GetMyChamberACC", "GetMyChamberGEN", "GetMyChamberPREP",
    "GetMyDuelWeaponACC", "GetMyDuelWeaponINS",
    "GetMyDuelWeaponNoHandsACC", "GetMyDuelWeaponNoHandsNoGunACC",
    "GetMyDuelWeaponNoHandsNoGunINS", "GetMyDuelWeaponNoPistolINS",
    "GetNaEn", "GetNaIn", "GetNaOn", "GetNoneE", "GetNumenFOA", "GetOyEm",
    "GetOyIm", "GetOyOgo", "GetOyOm", "GetOyYm", "GetOyaOy", "GetPetCat",
    "GetPetCatACC", "GetPetCatEndA", "GetPetCatGEN", "GetPetCatHersHis",
    "GetPetCatName", "GetPetCatSheHe", "GetPrincessPrinceGEN",
    "GetRandomChineseRegionGEN", "GetRandomChineseRegionPREP",
    "GetRandomPlanetNameGEN", "GetRegionalBigAnimalACC", "GetRelAdj",
    "GetRelAdjCap", "GetRelGroupAdj", "GetRelGroupNick",
    "GetReligionAdherentINS", "GetReligionAdherentsGENACC",
    "GetReligionFullName", "GetReligionGroupFullName",
    "GetReligionGroupPersons", "GetReligionGroupPersonsDAT",
    "GetReligionGroupPersonsGEN", "GetReligionHighGodACC",
    "GetReligionHighGodDAT", "GetReligionHighGodGEN",
    "GetReligionHighGodINS", "GetReligionNameGEN",
    "GetReligionScriptureACC", "GetReligionScriptureGEN",
    "GetReligionWarriorPluralGEN", "GetReligiousPersons",
    "GetReligiousRiteGEN", "GetRootDeadRelationGEN", "GetRootEndEA",
    "GetRootFromInsultNoun", "GetRootRelationACC", "GetRootRelationDAT",
    "GetRootRelationGEN", "GetRootRelationINS", "GetRulersRoomACC",
    "GetRulersRoomPREP", "GetSecretReligionScriptureAdjAndNameACC",
    "GetSecretReligionScriptureAdjAndNameGEN",
    "GetSecretReligionScriptureNameGEN", "GetSelectedIngredient_1GEN",
    "GetShortAdjective", "GetShortBaseName",
    "GetShortChineseEmperorNameDAT", "GetShortChineseEmperorNameGEN",
    "GetShortGenericNameGEN", "GetSkinDescription",
    "GetSmithFemalePostfix", "GetSmithMalePrefix", "GetSocietyName",
    "GetSocietyNameCap", "GetSocietyNameDAT", "GetSocietyNameGEN",
    "GetSoftEyEm", "GetSoftNaEn", "GetSoftNitseyEm", "GetSoftNitsuYa",
    "GetSoftNitsyYa", "GetSonDaughterACC", "GetSonDaughterDAT",
    "GetSonDaughterGEN", "GetStandardInsult", "GetToMarry",
    "GetTruReligionPerson", "GetTrueReligionFullName",
    "GetTrueReligionGroupPersonsDAT", "GetTrueReligionGroupPersonsGEN",
    "GetTrueReligionHighGodDAT", "GetTrueReligionHighGodGEN",
    "GetTrueReligionHighGodVOC", "GetTrueReligionScriptureAdjAndNameGEN",
    "GetTsaK", "GetTseKu", "GetTseyKom", "GetTsuKa", "GetTsuKaOpp",
    "GetTsyKa", "GetUEgo", "GetUOgo", "GetUyuEgo", "GetUyuOgo",
    "GetWLDieNameGEN", "GetWarriorLodgeSymbolShortCapGEN",
    "GetWarriorRoleCapGEN", "GetWeaponInjuringBlowOnMeAfterEffect",
    "GetWeaponTypeAdjPostfix2", "GetWeaponTypeAdjSoftPostfix",
    "GetWeaponsmithWeaponACC", "GetWeaponsmithWeaponGEN",
    "GetWonderAyaIyIeOe", "GetWonderAyaYyYeOe", "GetWonderItAt",
    "GetWonderTerrainPREP", "GetWonderTypeShortCapGEN",
    "GetWonderTypeShortCapPREP", "GetWonderTypeShortGEN",
    "GetWonderYetYut", "GetYGo", "GetYMu", "GetYkaIn", "GetYnaIn",
    "GetYuEgo", "GetZeusJupiterNameGEN", "_",
]

# --- Harvested per game and target language ---------------------------------
#
# The technique above is not a Russian one. Every inflecting language reaches
# for it, and Russian is not even the loudest: French HOI4 adds 117 functions
# over 37 270 occurrences against Russian's 33 over 5 922. Chinese, Japanese
# and Korean add almost nothing at all — they do not inflect, so there is
# nothing to harvest.
#
# How these were taken (2026-08-20, from the installed games): every `[...]`
# token, string arguments stripped first so prose inside `Select_CString` does
# not leak in; keep the names present in the translation and never in English;
# drop the tooling tag `LocEditor`; drop names that differ from an English one
# only by case (`getadjective`) or by a single letter (`GetAdjectice`) — such a
# call does not fire in the game and forgiving it would hide a real fault; keep
# numbered variants of a known name (`HighGodName2`), because that is how CK3
# spells its case forms. Plain lowercase_with_underscores names are keys, not
# calls, and are dropped.
#
# No frequency threshold: a repeated typo passes any of them (Polish HOI4 says
# `getadjective` 31 times), while a threshold of five would have cut 13 real
# Russian HOI4 functions out of 33. The criterion above reproduces the
# hand-made `HOI4_RU_CALLS` exactly, 33 of 33. CK2 is the one exception — its
# translations invent hundreds of one-off helpers, so a cutoff of five keeps
# the list to a workable size and the coverage is recorded per language.
LANGUAGE_CALLS: dict[tuple[str, str], list[str]] = {
    # Crusader Kings II, German — 41 functions over 4176 occurrences, 96.8% of occurrences.
    ("ck2", "de"): [
        "GetDerDie", "GetDieserDiese", "GetEinEine", "GetEuerEure",
        "GetEuremEurer", "GetEurenEure", "GetHerHimCap", "GetHoldingdiedasden",
        "GetHouseOfWorshipiminder", "GetHouseOfWorshipzumzur", "GetIhmIhr",
        "GetMOCodedemder", "GetMOCodedieden", "GetMannesFrau",
        "GetReligionWarrior", "GetUnserUnsere", "GetWeaponAdjEndingDE",
        "GetWeaponTypeDE", "Getdemder", "Getdendie", "Getderdie", "Getdesder",
        "Getdiesemdieser", "GeteFemale", "GeteMale", "Geteineine",
        "GeteineineOpp", "Geteinemeiner", "Geteineneine", "Geteineseiner",
        "GetemMale", "GeterFemale", "Getihmihr", "Getihnsie", "GetinFemale",
        "Getmeinemmeiner", "GetnMale", "GetrMale", "GetsMale",
        "Getunseresunserer", "Getzumzur",
    ],
    # Crusader Kings II, Spanish — 21 functions over 3807 occurrences, 98.4% of occurrences.
    ("ck2", "es"): [
        "FromFromGetTitledFirstName", "FromGetTitledFirstName", "GetAlAla",
        "GetAlAlaCap", "GetDelDela", "GetEA", "GetElElla", "GetElEllaCap",
        "GetElLa", "GetElLaCap", "GetLoLa", "GetLoLaCap", "GetOA", "GetOAOpp",
        "GetOnOna", "GetReligionWarrior", "GetRleRla", "GetRleRlaCap",
        "GetSpanishCatolica", "GetXA", "GetXAOpp",
    ],
    # Crusader Kings II, French — 127 functions over 26293 occurrences, 99.5% of occurrences.
    ("ck2", "fr"): [
        "GetAuAla", "GetAuAlaCap", "GetCapitalHoldingAuAla",
        "GetCapitalHoldingDuDela", "GetCeluiCelle", "GetCeluiCelleCap",
        "GetCultureMasc", "GetCultureMascFem", "GetCultureMascPl", "GetDDe",
        "GetDWDevilDuDela", "GetDuDela", "GetEEsse", "GetEEtte", "GetEauElle",
        "GetEluiElle", "GetErEre", "GetEtEte", "GetEtEtte", "GetEurEresse",
        "GetEurRice", "GetEvilGodDuDelaDes", "GetEvilGodLeLaLes", "GetFVe",
        "GetFromFromRootInsultNounAdj", "GetFromRootComplimentNounAdj",
        "GetFromRootInsultNounAdj", "GetGovernmentMasc", "GetHoldingDuDela",
        "GetHouseLeLa", "GetHouseOfWorshipDuDela", "GetHouseOfWorshipUnUne",
        "GetIeuxIeille", "GetIlElle", "GetIlElleCap", "GetIlElleOpp", "GetLLa",
        "GetLLaCap", "GetLLle", "GetLeLa", "GetLeLaCap", "GetLuiElle",
        "GetNNne", "GetOnA", "GetOnAOpp", "GetOuOlle", "GetRSe",
        "GetReligionMasc", "GetReligionMascFem", "GetReligionMascPl",
        "GetReligiousGroupFem", "GetReligiousGroupMascFem",
        "GetReligiousGroupMascPl", "GetReligiousPersonMascFem",
        "GetRootFromComplimentNounAdj", "GetRootFromFromInsultNounAdj",
        "GetRootFromInsultNounAdj", "GetSSse", "GetSilSielle",
        "GetSilSielleCap", "GetXSe", "Get_Au_TitledFirstName",
        "Get_Au_TitledName", "Get_E", "Get_EOpp", "Get_Le_HighGod",
        "Get_Le_SocietyRank", "Get_Le_TitledFirstName",
        "Get_Le_TitledFirstNameJ", "Get_Le_TitledName", "Get_Le_TitledNameJ",
        "Get_au_BodyPartInjured", "Get_au_HighGod", "Get_au_HighGodTrue",
        "Get_au_Society", "Get_au_TitledFirstName", "Get_au_TitledFirstNameJ",
        "Get_au_TitledName", "Get_au_TitledNameJ", "Get_du_HighGod",
        "Get_du_HighGodTrue", "Get_du_JobTitle", "Get_du_Realm",
        "Get_du_RealmFull", "Get_du_Scripture", "Get_du_ScriptureSecret",
        "Get_du_SelectedIngredient_1", "Get_du_Society", "Get_du_SocietyRank",
        "Get_du_TitledFirstName", "Get_du_TitledFirstNameJ",
        "Get_du_TitledName", "Get_du_TitledNameJ", "Get_e_JobTitle",
        "Get_e_SelectedIngredient_1", "Get_e_SelectedIngredient_2",
        "Get_e_SocietyRank", "Get_en_Realm", "Get_juifs", "Get_le_HighGod",
        "Get_le_HighGodTrue", "Get_le_JobTitle", "Get_le_Realm",
        "Get_le_RealmFull", "Get_le_Scripture", "Get_le_ScriptureSecret",
        "Get_le_SelectedIngredient_1", "Get_le_Society", "Get_le_SocietyRank",
        "Get_le_TitledFirstName", "Get_le_TitledFirstNameJ",
        "Get_le_TitledName", "Get_le_TitledNameJ", "Get_on_BodyPartInjured",
        "Get_on_DuelWeapon", "Get_on_JobTitle", "Get_only_Au_Title",
        "Get_only_Le_JobTitle", "Get_only_Le_Title", "Get_only_au_Title",
        "Get_only_du_Realm", "Get_only_du_RealmFull", "Get_only_du_Society",
        "Get_only_du_Title", "Get_only_e_Title", "Get_only_le_Society",
        "Get_only_le_Title",
    ],
    # Crusader Kings III, French — 13 functions over 357 occurrences.
    ("ck3", "fr"): [
        "DivineRealm2", "DivineRealm3", "HighGodName2", "HouseOfWorship2",
        "HouseOfWorship3", "HouseholdGodNamePossessive", "NegativeAfterLife3",
        "PantheonTerm2", "PantheonTerm3", "PositiveAfterLife2",
        "ReligiousText3", "WarGodHerHim", "WitchGodNamePossessive",
    ],
    # Crusader Kings III, Polish — 22 functions over 445 occurrences.
    ("ck3", "pl"): [
        "CreatorSheHe", "FertilityGodSheHe", "GetBaronyNameExplicitlyGetName",
        "GetBuildingTypeText", "GetDefinitiveNameGetName",
        "GetDefinitiveNameNoTier", "GetDescriptionGetName", "GetGirlBoy",
        "GetHeShe", "GetHisHer", "GetShortUINameNoTooltipNotMe",
        "GetShortUINameNotMeNoFormat", "GetShortUINameNotMeNoTooltipNoFormat",
        "GetTitleAsNameGetName", "HealthGodSheHe", "HouseholdGodNamePossessive",
        "IsHostile", "IsPowerfulVassal", "KnowledgeGodSheHe", "WealthGodSheHe",
        "WitchGodNamePossessive", "random_GoodGodNamesPossessive",
    ],
    # Crusader Kings III, Russian — 10 functions over 440 occurrences.
    ("ck3", "ru"): [
        "GetAdjectiveWithNoTooltip", "GetAdjectuve", "GetCourt_RU_WhereTo",
        "GetNamePossessiveNoFormat", "GetNamePossessiveOrMyNoTooltip",
        "GetPositionNameNoTooltip", "GetTitledFirstNamePossessiveOrMy",
        "HouseholdGodNamePossessive", "IsLocaFemale", "WitchGodNamePossessive",
    ],
    # Hearts of Iron IV, French — 117 functions over 37270 occurrences.
    ("hoi4", "fr"): [
        "AdjFS", "AdjMS", "AuEnANP", "GET_AUSTRALIA_NEW_ZEALAND_STATUS_FR",
        "GeLeader", "GetAOnt", "GetAOntInterrNP", "GetAOntNP", "GetAdMP",
        "GetAdMS", "GetAdjFP", "GetAdjFS", "GetAdjFs", "GetAdjHabitants",
        "GetAdjMP", "GetAdjMS", "GetAdjMs", "GetAuAlaAlNP", "GetAuAlaIdeo",
        "GetAuEnANP", "GetAuEnANPCap", "GetAuEnAnNP",
        "GetAuquelAlaquelleAuxquelsNP", "GetBalticAxisInvesmentsAdj_FR",
        "GetCeluiCelleNP", "GetCeluiCelleNPCap", "GetCestCesontNP",
        "GetDNentNP", "GetDeluiDelleDeuxNP", "GetDuDeDNP", "GetDuDelaDeLNP",
        "GetDuDelaDelNP", "GetDuDelaDesFNP", "GetDuDelaIdeo", "GetEEntNP",
        "GetEauElleEauxNP", "GetElElleElsNP", "GetEnAuANP", "GetErEreErsNP",
        "GetErErePers", "GetEstSont", "GetEstSontNP", "GetFP", "GetFaitFontNP",
        "GetGetLeLaLNP", "GetHAbitants", "GetHabitants", "GetHerosHeroinePers",
        "GetIdeoAdjFPInan", "GetIdeoAdjFSInan", "GetIdeoAdjMPAnim",
        "GetIdeoAdjMPInan", "GetIdeoAdjMSAnim", "GetIdeoAdjMSInan",
        "GetIdeologie", "GetIlElleNP", "GetIlElleNPCap", "GetIlEllePers",
        "GetIlEllePersCap", "GetLLLesFNP", "GetLLesFNP", "GetLaLeLNPCap",
        "GetLeLaFNP", "GetLeLaFNPCap", "GetLeLaFPers", "GetLeLaLDirCap",
        "GetLeLaLIdeo", "GetLeLaLNP", "GetLeLaLNPCap", "GetLeLaNPCap",
        "GetLeLalNP", "GetLuiElleDir", "GetLuiElleEux", "GetLuiElleEuxNP",
        "GetLuiElleEuxNPCap", "GetLuiEllePers", "GetLuiLeur", "GetLuiLeurNP",
        "GetLuiLeurNPCap", "GetMS", "GetNameLeLaLNP",
        "GetNaturaResource_BAL_FR", "GetNestNesontNP", "GetQueluiQuelleQueuxNP",
        "GetSaLeurNP", "GetSaLeurNPCap", "GetSesLeursNP", "GetSesLeursNPCap",
        "GetSestSesontNP", "GetSilSielleNP", "GetSilSielleNPCap",
        "GetSilSiellePers", "GetSonLeur", "GetSonLeurNP", "GetSonLeurNPCap",
        "GetSovietOppositionName_AlAlaAux", "GetSovietOppositionName_LLaLes",
        "GetTEntNP", "GetTLentNP", "GetTNentNP", "GetTSentNP", "GetTSsentNP",
        "GetTTtentNP", "GetTVentNP", "GetUnUneDesNP", "GetUnUneDesNPCap",
        "GetXENP", "GetXEPers", "GetXEntNP", "GetXSNP", "LeLaLNP",
        "NORDIC_get_adjective_ADJ_MS_FR",
        "NORDIC_get_alliance_name_DuDelaDel_FR",
        "NORDIC_get_alliance_name_LeLaL_FR", "SWI_FROM_or_fake_country_word_FR",
        "SWI_get_fascist_neighbor_INHAB_des",
        "SWI_get_fascist_neighbor_INHAB_les",
    ],
    # Stellaris, German — 137 functions over 1159 occurrences.
    ("stellaris", "de"): [
        "DenDieDE", "GestSpeciesNamePlural", "GetBrainNameDE2",
        "GetBrainNameDE3", "GetBuildingGrowingCap", "GetCommunityOrImperiumDE1",
        "GetCommunityOrImperiumDE2", "GetCommunityOrImperiumDE3", "GetDEIhnSie",
        "GetDemDerDE", "GetDenDieDE", "GetDerDes", "GetDerDie", "GetDerDieCap",
        "GetDerDieDE", "GetDerDieDECap", "GetDerDieDeCap", "GetDesDer",
        "GetDesDerDE", "GetDessenDerenDE", "GetDistressNamePlural",
        "GetEFemale", "GetEFemaleDE", "GetEFemaleeDE", "GetEMaleDE",
        "GetEarName", "GetEmErDE", "GetEnEDE", "GetEnvoyDE1", "GetEnvoyDE2",
        "GetEnvoyDE3", "GetEnvoyDE4", "GetErEDE", "GetExplorerPlural",
        "GetFinancialAdvisorAgencyCapDE1", "GetGalCommunityOrGalImperiumDE1",
        "GetGalCommunityOrGalImperiumDE2", "GetGalCommunityOrGalImperiumDE3",
        "GetGalCommunityOrGalImperiumDE3Cap", "GetGalCommunityOrGalImperiumDE4",
        "GetGalCommunityOrGalImperiumDE5", "GetGalCouncilOrImpCouncilDE1",
        "GetGalCouncilOrImpCouncilDE2", "GetGalCouncilOrImpCouncilDE3",
        "GetGalCouncilOrImpCouncilDE4", "GetGetDemDerDE", "GetGetIhnSieDE",
        "GetHerHer", "GetIhmIhrDE", "GetIhnSieDE", "GetInFemaleDE",
        "GetLeaderStatusAdj", "GetLeviathanParadeNameDE1",
        "GetLeviathanTargetNameDE1", "GetLeviathanTargetNameDE2",
        "GetLeviathanTargetNameDE3", "GetLeviathanTargetNameDE4",
        "GetLeviathanTargetNameDE5", "GetLeviathanTargetNameDE6",
        "GetLeviathanTargetNameDE7", "GetMDerDieDE", "GetMREndingDE",
        "GetNMale", "GetNMaleDE", "GetNewAgeDE1", "GetNewAgeDE2",
        "GetOppositionGalcomLobbyistsDE1", "GetOppositionGalcomLobbyistsDE2",
        "GetPlanetArkshipDE", "GetPlanetHabitatDE1", "GetPlanetHabitatDE2",
        "GetPlanetHabitatDE3", "GetPlanetHabitatDE4", "GetPlanetHabitatDE5",
        "GetPlanetHabitatDE6", "GetPlanetHabitatDE7", "GetPlanetHabitatDE8",
        "GetPlanetHabitatDE9", "GetPlanetMoonCap", "GetPlanetMoonDE2",
        "GetPreFTLUpperDE1", "GetRMaleDE", "GetResearchersDE1",
        "GetRulerGetDemDerDE", "GetSMale", "GetSMaleDE", "GetSREndingDE",
        "GetScientistDE1", "GetScientistDE10", "GetScientistDE2",
        "GetScientistDE3", "GetScientistDE4", "GetScientistDE5",
        "GetScientistDE6", "GetScientistDE7", "GetScientistDE8",
        "GetScientistDE9", "GetScientistPluralDE1", "GetShroudPatronDE1",
        "GetShroudPatronDE2", "GetShroudPatronDE3", "GetShroudPatronDE4",
        "GetShroudPatronDE5", "GetSieIhnDE", "GetSkinTypeDE1", "GetSkinTypeDE2",
        "GetSpecies", "GetSpeciesAdjective", "GetSpeciesClassName",
        "GetSpeciesNameAdj", "GetSpeciesNameInsultPlural",
        "GetSpeciesNamePluralen", "GetStarlightVanguardNameDE1",
        "GetStarlightVanguardNameDE2", "GetTeamMemberDE1", "GetTeamMemberDE2",
        "GetTeamMemberDE5", "GetTransferenceVolunteerDronePlural",
        "GetTrophyNameDE1", "GetTrophyNameDE2", "GetTrophyNameDE3",
        "GetTrophyNameDE4", "GetTrophyNameDE5", "GetUnseresUnsererDE",
        "GetVomVonderDE", "GetWorkerPlural", "GetXEDE", "GetXInDE",
        "GetZumZurDE", "GeteFemale", "GetinFemaleDE", "GetsMale", "GetsMaleDE",
        "HeSheCap", "IhnSieDe", "Name", "Standard",
    ],
    # Stellaris, French — 206 functions over 2396 occurrences.
    ("stellaris", "fr"): [
        "AlloysProducerResources_lower", "AlloysProducerWithIcon_lower",
        "AlloysProducer_lower", "ClassPrefixColor_FR",
        "ConsumerGoodsProducerWithIcon_lower", "EnergyProducerWithIcon_lower",
        "FoodProducerWithIcon_lower", "GetAlloyProducerPlural_lower",
        "GetAuAlaAlCommGalEmpGal", "GetAuAlaAlDir", "GetAuAlaFDir",
        "GetAuAlaFDirCap", "GetAuAlaLead", "GetAuteur",
        "GetBureaucratPluralWithIcon_lower", "GetBureaucratPlural_lower",
        "GetCatalyticMineralsOrFood_LeLaLes_FR", "GetCeluiCelleDir",
        "GetCeluiCelleLead", "GetCeluiCelleLeadCap", "GetCitizen",
        "GetCorpRulerJobPlural_lower", "GetCrimeDeviancy_lower",
        "GetDeluiDelleLead", "GetDiplomacyTraditionNameArticle",
        "GetDuDelaDelCommGalEmpGal", "GetDuDelaDelDir", "GetDuDelaFDir",
        "GetDuDelaLead", "GetEauElleLead", "GetElElleDir", "GetElElleLead",
        "GetEngineerPlural_lower", "GetErEreDir", "GetErEreLead",
        "GetEurEresseLead", "GetEurEuseLead", "GetEurRiceLead", "GetEuxEuseDir",
        "GetEuxEuseLead", "GetExperimentalEngineerPlural_lower",
        "GetExplorerPlural", "GetFVeLead", "GetFarmerPlural_lower",
        "GetGeneticMutationNamePlural", "GetHealthcareSwapPluralWithIcon_lower",
        "GetHeroHeroineLead", "GetHiveAuthorityPlural", "GetIerEresseLead",
        "GetIlElleDir", "GetIlElleDirCap", "GetImplantNamePlural",
        "GetInstrumentCravingIconAndName_FR_ded",
        "GetInstrumentCravingIconAndName_FR_lower", "GetJob_gender_lower_FR",
        "GetLeLaFDir", "GetLeLaFDirCap", "GetLeLaLCommGalEmpGal",
        "GetLeLaLCommGalEmpGalCap", "GetLeLaLDir", "GetLeLaLDirCap",
        "GetLeLaLead", "GetLeLaLeadCap", "GetLeaderClass_Cap_FR",
        "GetLeaderClass_LeLaL_FR", "GetLeaderClass_LeLaL_FR_Cap",
        "GetLeaderClass_lower_FR", "GetLeviathanTargetName_DuDela_FR",
        "GetLeviathanTargetName_LeLa_Cap_FR", "GetLeviathanTargetName_LeLa_FR",
        "GetLuiElleDir", "GetLuiElleLead", "GetLuiElleLeadCap",
        "GetMedicalFacilityPlural", "GetMedicalImplantNamePlural", "GetN",
        "GetNamePlural_lower", "GetName_lower", "GetOnALead", "GetOnELead",
        "GetParadeStudy_DelaDel_FR", "GetParadeStudy_LaL_Cap_FR",
        "GetParadeStudy_LaL_FR", "GetPiece", "GetPlanetMoonCap",
        "GetPopAssemblersPluralWithIcon_lower", "GetPopTypeNamePlural",
        "GetPriestPlural_lower", "GetPriest_lower", "GetQueluiQuelleDir",
        "GetQueluiQuelleLead", "GetResearcherPluralWithIcon_lower",
        "GetResearchers_lower", "GetScientistPlural_lower",
        "GetScientist_FR_IlElle", "GetScientist_FR_IlsElles",
        "GetScientist_FR_XE", "GetScientist_FR_euxelles",
        "GetScientist_FR_ilelle", "GetScientist_FR_ilselles",
        "GetScriptedLeaderRecruitedGreeting_FR", "GetSensation_lower",
        "GetSeperatistAid_FR_en", "GetServiteurServanteDir",
        "GetShroudPatron_FR_LeLaLes", "GetShroudPatron_FR_aont",
        "GetShroudPatron_FR_dudeldes", "GetShroudPatron_FR_eent",
        "GetShroudPatron_FR_ilils", "GetShroudPatron_FR_lelales",
        "GetShroudPatron_FR_luieux", "GetShroudPatron_FR_saleur",
        "GetShroudPatron_FR_sonleur", "GetSilSielleDir", "GetSilSielleLead",
        "GetSilSielleLeadCap", "GetSireDameLead", "GetSireDameLeadCap",
        "GetSireMadameLead", "GetSireMadameLeadCap", "GetSoldierPlural_lower",
        "GetSpecialistPlural_lower", "GetSpecialist_lower",
        "GetStartingDriveSingular_DuDel_FR", "GetSubMantleLower_FR_fs",
        "GetSubMantleLower_FR_mp", "GetSubMantleLower_FR_ms", "GetT1DepEnergy",
        "GetT1DepEngineering", "GetT1DepMinerals", "GetT1DepPhysics",
        "GetT1DepSociety", "GetT1LumpEnergy", "GetT1LumpEngineering",
        "GetT1LumpMinerals", "GetT1LumpPhysics", "GetT1LumpSociety",
        "GetT2DepEnergy", "GetT2DepEngineering", "GetT2DepMinerals",
        "GetT2DepPhysics", "GetT2DepSociety", "GetT2LumpEnergy",
        "GetT2LumpEngineering", "GetT2LumpMinerals", "GetT2LumpPhysics",
        "GetT2LumpSociety", "GetT3DepEnergy", "GetT3DepEngineering",
        "GetT3DepMinerals", "GetT3DepPhysics", "GetT3DepSociety",
        "GetT3LumpEnergy", "GetT3LumpEngineering", "GetT3LumpMinerals",
        "GetT3LumpPhysics", "GetT3LumpSociety", "GetT4DepEnergy",
        "GetT4DepEngineering", "GetT4DepMinerals", "GetT4DepPhysics",
        "GetT4DepSociety", "GetT4LumpEnergy", "GetT4LumpEngineering",
        "GetT4LumpMinerals", "GetT4LumpPhysics", "GetT4LumpSociety",
        "GetTelepathSwapPluralWithIcon_lower", "GetTelepath_lower",
        "GetTestSubjectPlural_lower", "GetTraderSwapPluralWithIcon_lower",
        "GetTrophyName_AuAla_FR", "GetTrophyName_DuDela_FR",
        "GetTrophyName_LeLa_Cap_FR", "GetTrophyName_LeLa_FR",
        "GetTrophyName_XE_FR", "GetUnitDroneCap", "GetWorkerPlural_lower",
        "GetWorker_lower", "GetWranglerJobNamePlural_lower",
        "GetXECommGalEmpGal", "GetXEDir", "GetXELead", "GetXLeLead",
        "GetXNeLead", "GetXSseLead", "GetXTeLead", "GetXTteLead",
        "MineralsProducerWithIcon_lower", "OverlordConsumes_FR_lela",
        "Paragon_Origin_Antislavers", "Paragon_Origin_Authority",
        "Paragon_Origin_Conditions", "Paragon_Origin_Ethos",
        "Paragon_Origin_Freedoms", "Paragon_Origin_Loved",
        "Paragon_Origin_Nobles", "Paragon_Origin_Past_Deals",
        "Paragon_Origin_Pay", "Paragon_Origin_Prisoners",
        "Paragon_Origin_Sided_Democrats", "Paragon_Origin_Strong_Gov",
        "Paragon_Origin_War", "ResearchProducerWithIcon_lower",
        "SubjectResearcherUpkeep_FR_lela", "WildernessGladeProvides_FR_lela",
    ],
    # Stellaris, Brazilian Portuguese — 103 functions over 287 occurrences.
    ("stellaris", "pt"): [
        "Acanhado", "Afinal", "Alegre", "Amante", "Anjo", "Ao", "At",
        "Aterrorizado", "Aterrorizante", "Ballardskater", "Bellevue", "Bode",
        "Bomb", "Bravio", "Busca", "Ca", "Conclus", "Condu", "Contente",
        "Contesta", "Contudo", "Contumaz", "Cotovia", "De", "Desanimado",
        "Desaplicado", "Descontente", "Descrente", "Desde", "Desguardado",
        "Diamante", "Direto", "Do", "Docinho", "Dorminhoco", "Doutor",
        "Doutrinador", "E", "Ef", "Efervescente", "Elimina", "Encarnado",
        "Enganado", "Enrugado", "Equivocado", "Espont", "Eterno", "Flagelo",
        "Fora", "GetExplorerPlural", "GetLastName", "GetOACommImp",
        "GetOAGalCommImp", "GetOAGalCommImpCap", "GetSpeciesClassName",
        "GetSpeciesNamePluralInsultCap", "GetSpeciesSpawnNamePluralCap",
        "Ideia", "Ign", "Imbecil", "Impiedoso", "Inabal", "Incans",
        "Indelicado", "Indisciplinado", "Inesperado", "Inocente",
        "Insuficiente", "Insuport", "Irreprim", "Irritante", "Jenny", "Lament",
        "Legeteuse", "Liberta", "Ligas", "M", "Malvestido", "Melhor",
        "Movimento", "Neon", "Normalmente", "Observa", "Ocasional", "Padr",
        "Pedante", "Perfeccionista", "Perigo", "Perspicaz", "Pessimista",
        "Porteiro", "Preserva", "Proibido", "Queridinho", "Resmung", "Root",
        "Rosa", "Sagaz", "Santana", "Sem", "Sinistro", "Sobretudo", "Talho",
    ],
    # Stellaris, Russian — 49 functions over 2143 occurrences.
    ("stellaris", "ru"): [
        "GetAXX", "GetAlloyProducerPlural_lower", "GetArchaeologist",
        "GetBiologicalPops", "GetCommunityOrImperiumDE3",
        "GetCommunityOrImperium_RULOC_PREP", "GetCorpRulerJob",
        "GetCrimeDeviancy_lower", "GetExplorerPlural", "GetEyeNamePluralCap",
        "GetEyuIm", "GetFarmerPlural_lower", "GetGalCommunityOrGalImperiumDE1",
        "GetGalCommunityOrGalImperium_RULOC_GEN", "GetGetAXX",
        "GetGetPlanetMoon", "GetHerHimCap", "GetHomeWorldPlanetMoon",
        "GetInstrumentCravingIconAndName_FR_lower", "GetLeaderClass_lower_FR",
        "GetLeaderStatusAdj", "GetLeviathanTargetNameDE1", "GetMechanicalPops",
        "GetNameAdj", "GetNameGetName", "GetNejNem", "GetPlanetArkship_RULOC",
        "GetPlanetHabitatDE1", "GetPlanetHabitatDE2", "GetPlanetHabitatDE3",
        "GetPlanetHabitatDE4", "GetPlanetHabitatDE5",
        "GetPlanetHabitat_RULOC_PREP", "GetPlanetMoonCap", "GetPlural",
        "GetResearcherPluralCap", "GetResearcherPlural_RULOC_Nom_lower",
        "GetSoldierPlural_lower", "GetSpeciesAdjective", "GetTradingHubType",
        "GetTrophyNameDE1", "GetWorkerPlural_lower", "GetWorker_RU_Gen_Pl",
        "GetWranglerJobNameWithIcon", "GetXAA",
        "SubjectResearcherUpkeep_FR_lela", "SubjectResearcherUpkeep_RULOC_ACC",
        "WildernessGladeProvides_RULOC_ACC", "pre_ftl_planetGetName",
    ],
    # Russian HOI4 and CK2 keep the lists above verbatim: they were measured
    # against live translations, and the numbers in ARCHITECTURE.md rest on them.
    ("hoi4", "ru"): HOI4_RU_CALLS,
    ("ck2", "ru"): CK2_RU_CALLS,
}


# Calls that return an ending rather than a word: the text is glued straight
# onto them, so no space belongs there. Only Russian HOI4 separates the two —
# elsewhere the whole list doubles as the ending list.
LANGUAGE_ENDINGS: dict[tuple[str, str], list[str]] = {
    ("hoi4", "ru"): HOI4_RU_ENDINGS,
    ("ck2", "ru"): CK2_RU_CALLS,
}


def calls(game: str, locale: str) -> list[str]:
    """Inflection helpers the translation into `locale` uses in `game`."""
    return LANGUAGE_CALLS.get((game, locale), [])


def endings(game: str, locale: str) -> list[str]:
    """Of those, the ones text is glued onto without a space."""
    return LANGUAGE_ENDINGS.get((game, locale), [])

