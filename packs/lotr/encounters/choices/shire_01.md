---
id: shire_choice_01
type: choice
region: shire
leg: 1
meeting: green
probability_base: 0.05
probability_growth: 0.02
cooldown_km: 5
choices:
  - "help:Help him:morale+10"
  - "ignore:Walk on:morale-5"
  - "ask:Ask about the road:unlock:shire_rumor_01"
followups:
  help: "You spend twenty minutes gathering apples. The hobbit — his name is Milo — beams with gratitude and presses a warm apple pie into your hands. 'For the road!' Morale soars."
  ignore: "You step around the spill and walk on. Behind you, Milo mutters something about 'tall folk and their tall hurry.' The guilt gnaws at you."
  ask: "Milo scratches his chin. 'Road east? Aye, but mind the old forest path — travelers say they've heard strange songs on the wind.' He marks something on your map."
---

# The Lost Cart

Around the bend, a hobbit is struggling with an overturned cart. Apples spill across the path — dozens of them, rolling into the ditch. He looks up as you approach, face red with effort and embarrassment.

"Oh! Hullo! Bit of a disaster, as you can see. These apples were meant for the market at Bywater..."

He glances at the scattered fruit, then back at you, hopeful.
