-- ==========================================================================
-- Seed 15 Kauai activities for RoamAI
--
-- Assumes:
--   - Kauai destination exists with id = 1
--     (verify with: SELECT id, name FROM destinations WHERE name = 'Kauai';)
--   - Update destination_id in the INSERTs below if your Kauai id is different
--
-- Mix of activity categories:
--   - hiking, beach, water_sports, viewpoint, nature (outdoor, weather-sensitive)
--   - dining, cultural, shopping (indoor, weather-safe backups)
--
-- weather_sensitive flag drives the agent's reschedule logic:
--   TRUE  = agent will move this activity if rain/high AQI is forecast
--   FALSE = agent can use these as backup slots on bad-weather days
-- ==========================================================================

-- Uncomment and adjust if your destination_id is different:
-- \set kauai_id (SELECT id FROM destinations WHERE name = 'Kauai' LIMIT 1)

-- ==========================================================================
-- Outdoor activities (weather-sensitive)
-- ==========================================================================

INSERT INTO activities (destination_id, name, category, description, weather_sensitive, duration_hours, source) VALUES
(1, 'Kalalau Trail',
 'hiking',
 'An 11-mile coastal hiking trail along the rugged Napali Coast on Kauai''s north shore. Considered one of the most spectacular and challenging day hikes in the world, with dramatic sea cliffs, tropical valleys, hidden waterfalls, and secluded beaches. Requires permits for the full trail; the first 2 miles to Hanakapiai Beach are open to day hikers.',
 TRUE, 8.0, 'wikipedia'),

(1, 'Poipu Beach',
 'beach',
 'A crescent-shaped beach on Kauai''s sunny south shore, consistently ranked among the best beaches in the United States. Ideal for swimming, snorkeling, and spotting endangered Hawaiian monk seals. Two protected coves separated by a sandbar, one calm for children and one open to the ocean for stronger swimmers.',
 TRUE, 3.0, 'wikipedia'),

(1, 'Waimea Canyon',
 'viewpoint',
 'Known as the Grand Canyon of the Pacific, Waimea Canyon is 10 miles long, one mile wide, and over 3,600 feet deep, with dramatic red and green cliffs, cascading waterfalls, and sweeping views. Multiple lookout points along Waimea Canyon Drive offer stunning photo opportunities. Best visited in morning for clearest views before afternoon clouds roll in.',
 TRUE, 2.5, 'wikipedia'),

(1, 'Napali Coast Boat Tour',
 'water_sports',
 'A guided catamaran or Zodiac raft tour along the Napali Coast, viewing towering sea cliffs, hidden waterfalls, sea caves, and marine wildlife including dolphins, sea turtles, and seasonal humpback whales. Available only from May through October when ocean conditions are calm. Most tours include snorkeling stops.',
 TRUE, 5.0, 'wikipedia'),

(1, 'Wailua River Kayak',
 'water_sports',
 'A gentle kayak journey up the Wailua River, Hawaii''s only navigable river, through lush jungle to the Secret Falls hiking trail. The paddle is peaceful and suitable for beginners, followed by a short hike through the rainforest to a 100-foot waterfall with a swimming pool at its base. Perfect for calm, sunny days.',
 TRUE, 4.0, 'wikipedia'),

(1, 'Hanalei Bay',
 'beach',
 'A two-mile-long crescent bay on Kauai''s north shore, framed by lush green mountains with cascading waterfalls after rain. Excellent for surfing in winter, swimming and paddleboarding in summer. The charming town of Hanalei offers restaurants, shops, and a historic pier ideal for sunset walks.',
 TRUE, 3.0, 'wikipedia'),

(1, 'Sleeping Giant Trail',
 'hiking',
 'A moderate 3.4-mile round-trip hike up the Nounou Mountain range on Kauai''s east side, ending at panoramic views of coastline, mountains, and Wailua River valley. Named for the mountain''s silhouette resembling a reclining giant. Well-shaded through the forest sections; open ridge at the top can be windy.',
 TRUE, 2.5, 'wikipedia'),

(1, 'Anini Beach',
 'beach',
 'A quiet, family-friendly beach on Kauai''s north shore, protected by the longest fringing reef in the Hawaiian Islands. Calm, shallow waters make it one of the safest beaches for young children and beginner snorkelers. Grassy area with picnic tables and few crowds even in high season.',
 TRUE, 2.5, 'wikipedia'),

(1, 'Spouting Horn',
 'viewpoint',
 'A natural blowhole on Kauai''s south shore where ocean waves surge through a lava tube and shoot up to 50 feet into the air, accompanied by a distinctive hissing sound. Free to view from a cliffside overlook. Best at high tide with strong surf; adjacent lawn area good for picnics with ocean views.',
 TRUE, 1.0, 'wikipedia'),

(1, 'Limahuli Garden',
 'nature',
 'A National Tropical Botanical Garden on Kauai''s remote north shore, showcasing native Hawaiian plants across terraced garden levels backed by dramatic Makana mountain. Self-guided or docent-led tours through ancient Hawaiian agricultural terraces still growing traditional taro. Small crowds, deep cultural and ecological significance.',
 TRUE, 2.0, 'wikipedia'),

(1, 'Wailua Falls',
 'viewpoint',
 'An 80-foot twin waterfall on Kauai''s east side, easily viewed from a roadside lookout with no hiking required. Made famous as the opening scene of the Fantasy Island TV series. Best in morning light. A short unofficial trail leads to the base but is steep and slippery — not recommended after rain.',
 TRUE, 0.5, 'wikipedia'),

(1, 'Kokee State Park',
 'nature',
 'A 4,345-acre park at 3,600 feet elevation on Kauai''s west side, featuring cool mountain air, hiking trails through native forests, and spectacular viewpoints overlooking Waimea Canyon and the remote Kalalau Valley. Home to native honeycreeper birds and the Kokee Natural History Museum. Cooler temperatures — bring a light jacket.',
 TRUE, 4.0, 'wikipedia'),

-- ==========================================================================
-- Indoor activities (weather-safe backups)
-- ==========================================================================

(1, 'Kauai Coffee Company Tour',
 'cultural',
 'A free self-guided walking tour through the largest coffee farm in the United States, with 3,100 acres of coffee trees on Kauai''s south shore. Sample multiple coffee varieties in the visitor center, watch a short film on Hawaiian coffee production, and browse the gift shop. Fully covered facilities — a good rainy-day activity.',
 FALSE, 1.5, 'wikipedia'),

(1, 'Kauai Museum',
 'cultural',
 'A cultural museum in downtown Lihue showcasing Kauai''s history from Polynesian settlement through the plantation era and modern day. Rotating exhibits on Hawaiian art, geology, and cultural artifacts. Small but well-curated; a good indoor option on rainy afternoons or when planning a break from beach and hiking activities.',
 FALSE, 1.5, 'wikipedia'),

(1, 'Duke''s Kauai',
 'dining',
 'A waterfront restaurant on Kalapaki Beach in Lihue, named after Hawaiian surfing legend Duke Kahanamoku. Menu features fresh local fish, tropical cocktails, and the famous hula pie for dessert. Open-air lanai seating with ocean views, though the interior offers a covered option in bad weather. Live Hawaiian music most evenings.',
 FALSE, 2.0, 'user_added');

-- ==========================================================================
-- Verify the seed
-- ==========================================================================

SELECT
    name,
    category,
    weather_sensitive,
    duration_hours,
    LEFT(description, 80) AS description_preview
FROM activities
ORDER BY weather_sensitive DESC, category, name;

-- Expected: 15 rows returned (12 outdoor + 3 indoor)
