# Thai flood management

This is a map of the institutions a call will bump into. It is not a procedure for BaanSafe to execute.

## The legal frame

The Disaster Prevention and Mitigation Act B.E. 2550 (2007) replaced the 1979 Civil Defence Act and the 1999 fire act. It came into force on 6 November 2007. It names the Department of Disaster Prevention and Mitigation (DDPM, กรมป้องกันและบรรเทาสาธารณภัย, ปภ.) as the department that coordinates national disaster work, and it gives local government a disaster role that has to line up with the provincial plan. At the top, the National Disaster Prevention and Mitigation Committee is chaired by the Prime Minister or a designated Deputy Prime Minister. Provinces have their own committees. Bangkok has a metropolitan committee. The Asian Disaster Reduction Center's country note is the clearest short English description: https://www.adrc.asia/nationinformation.php?Lang=en&NationCode=764

The national plan that sits under the Act is the National Disaster Risk Management Plan. English summaries usually point at the 2015 edition. Confirm which revision is in force before anyone treats a sentence in it as current policy.

## Who does what in a flood

**DDPM (Ministry of Interior).** Runs the national coordination machinery, the disaster academy, and the public reporting line. In a large flood it supports the province and can move teams and equipment when one province is overwhelmed. It is not the agency that measures the river.

**The provincial governor.** Under the Act the governor is the provincial director. In practice that means the governor chairs the provincial response, opens an incident command when told to, and is the person who can order evacuation and resource use inside the province. District chiefs carry that down. A Government Public Relations Department note from August 2024 told governors to stand up an incident command for water and told the public to call for help on 1567 or 1784, both free, 24 hours: https://prd.go.th/main/article/6ddb9b3d-e483-45db-a3eb-189085793ee5

**Local government and villages.** Municipalities, tambon administrative organisations, and village headmen are who actually knock on doors, open a temple or a school as a shelter, and know which lane is passable. A call that says "the district office already knows" may still need a provincial resource the local office does not have.

**TMD (Thai Meteorological Department, กรมอุตุนิยมวิทยา).** Rain, storms, and weather warnings. https://www.tmd.go.th A call about "they said the rain would stop" is a TMD question, not a rescue decision, until the water is already in the house.

**RID (Royal Irrigation Department, กรมชลประทาน).** Dams, barrages, and canals. A downstream flood can be a release decision rather than the rain over the caller's roof. Chao Phraya barrage releases are announced in advance and change the level along the river by tens of centimetres. https://www.rid.go.th DDPM situation notes routinely tell riverside provinces to prepare when RID writes to them.

**ONWR and the water command.** The Office of the National Water Resources (สำนักงานทรัพยากรน้ำแห่งชาติ) is the water-policy body: https://www.onwr.go.th During flood season a national water command is what English reports call the National Water Command Center. It is the place that looks across basins. It does not replace the governor. The public numbers announced with that command have been 1567 and 1784.

**GISTDA.** Satellite flood extent (1, 3, 7, 30 days) and repeat-flood frequency. Portals: https://disaster.gistda.or.th and https://flood.gistda.or.th The open feature API needs a key. Those maps are water on the ground as seen from space, not a list of households.

## 1784 and the path of a warning

1784 is DDPM's public hotline (สายด่วนนิรภัย). There is also the LINE account @1784DDPM. DDPM's own citizen guide for reporting an incident through 1784 and that LINE account is published from disaster.go.th, and it cites the 2007 Act as the related law: https://backofficeminisite.disaster.go.th/apiv1/apps/minisite_cco/204/sitedownload/32433/download?TypeMenu=MainMenu&filename=0fe814b34f8735c80c4c0933e4e910f7.pdf The hotline page is https://dpmreporter.disaster.go.th/portal/contact-us/hotline

A simplified path, as the institutions are set up, not as a script:

1. TMD, RID, and GISTDA describe rain, releases, and water extent.
2. The water command and DDPM pass that to provinces.
3. The governor decides what the province will do, including evacuation.
4. Districts and local officials tell people and open shelters.
5. People who are already in trouble call 1784 (or 1567 when that line is advertised), or they call a local leader who then calls up.

BaanSafe is a triage layer in front of step 5. It does not issue the evacuation order and it does not replace 1784.

## Relief payments, high level only

The Act and Interior Ministry / DDPM rules allow assistance after a disaster: death, injury, damaged housing, and immediate household needs. The baht amounts are in regulations and cabinet decisions and they are revised. This note deliberately does not copy a figure. Eligibility is a caseworker decision. That is why the route list has `aid_caseworker` and why an aid exception is on the "always requires a human" list in `config/escalation.yaml`. The scaffold must not approve or refuse a payment.
