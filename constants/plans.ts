// AETNA
// key: plan, value: starting link with tiered drug list
const aetna = {
    advancedControlChoicePlan: "https://client.formularynavigator.com/Search.aspx?siteCode=6147829214",
    advancedControlPlan: "https://client.formularynavigator.com/Search.aspx?siteCode=6135531453",
    advancedControlPlanAetna: "https://client.formularynavigator.com/Search.aspx?siteCode=6093234609",
    advancedControlPlanAetnaCalifornia: "https://client.formularynavigator.com/Search.aspx?siteCode=6095656895",
    aetnaHealthExchangePlanIndividual: "link",
    aetnaHealthExchangePlanSmallGroup: "link",
    aetnaStandardPlan: "link",
    aetnaStandardPlanDepartmentOfDefense: "link",
    basicControlPlan: "link",
    basicControlWithACSFPlan: "link",
    highValuePlan: "link",
    newJerseyEducatorsPlan: "link",
    standardControlChoicePlan: "link",
    standardControlChoiceWithACSFPlan: "link",
    standardControlPlan: "link",
    standardOptOutPlan: "link",
    standardOptOutPlanAetna: "link",
    standardOptOutPlanAetnaCalifornia: "link",
    standardOptOutWithACSFPlan: "link"
};

/*
Tier 1: Generic drugs
Tier 2: Preferred brand-name drugs
Tier 3: Non-preferred brand-name drugs
Tier 4: Preferred specialty drugs
Tier 5: Non-preferred specialty drugs
*/
const anthem = {
    essential: {
        threeTier: "https://client.formularynavigator.com/Search.aspx?siteCode=6878620461",
        fourTier: "https://client.formularynavigator.com/Search.aspx?siteCode=6873775889",
        fiveTier: "https://client.formularynavigator.com/Search.aspx?siteCode=5995764909",
    },
    national: {
        threeTier: "https://client.formularynavigator.com/Search.aspx?siteCode=2055289521",
        fourTier: "https://client.formularynavigator.com/Search.aspx?siteCode=2060134094",
        fiveTier: "https://client.formularynavigator.com/Search.aspx?siteCode=5974709652",
    },
    nationalDirect: {
        threeTier: "https://client.formularynavigator.com/Search.aspx?siteCode=1967600833",
        fourTier: "https://client.formularynavigator.com/Search.aspx?siteCode=1977662637",
        fiveTier: "https://client.formularynavigator.com/Search.aspx?siteCode=1987538112",
    },
    nationalDirectPlus: {
        threeTier: "https://client.formularynavigator.com/Search.aspx?siteCode=5016700249",
        fourTier: "https://client.formularynavigator.com/Search.aspx?siteCode=3795495313",
        fiveTier: "https://client.formularynavigator.com/Search.aspx?siteCode=4797317572",
    },
    select: "https://client.formularynavigator.com/Search.aspx?siteCode=0442274318",
    traditionalOpen: {
        threeTier: "https://client.formularynavigator.com/Search.aspx?siteCode=6000795811",
        fourTier: "https://client.formularynavigator.com/Search.aspx?siteCode=1242399477",
        fiveTier: "https://client.formularynavigator.com/Search.aspx?siteCode=7777329778",
    },
}
