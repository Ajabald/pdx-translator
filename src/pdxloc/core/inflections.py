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
