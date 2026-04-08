/**
 * SongSuggestions — Recommends songs that fit the singer's range.
 *
 * Song data is a curated static list — no API calls needed.
 * Songs are filtered by range overlap with the detected vocal range.
 * Users can filter by genre and difficulty.
 */

import { useMemo, useState } from "react";
import { hzToMidi } from "./VoiceTypeClassifier";

// ── Song database ──────────────────────────────────────────────────────────
// Fields: title, artist, midiLow, midiHigh, genre, difficulty
// difficulty: 'beginner' (≤9 st span), 'intermediate' (10-14 st), 'advanced' (15+ st)
// midiLow/midiHigh: MIDI note number of melody vocal range

const SONG_DATABASE = [
  // ── Beginner — narrow range, well-known melodies ────────────────────────
  { title: "Happy Birthday",              artist: "Traditional",              midiLow: 60, midiHigh: 72, genre: "Folk",        difficulty: "beginner" },
  { title: "Amazing Grace",              artist: "Traditional",              midiLow: 48, midiHigh: 60, genre: "Gospel",       difficulty: "beginner" },
  { title: "Country Roads",              artist: "John Denver",              midiLow: 50, midiHigh: 64, genre: "Country",      difficulty: "beginner" },
  { title: "Moon River",                 artist: "Andy Williams",            midiLow: 52, midiHigh: 64, genre: "Jazz",         difficulty: "beginner" },
  { title: "Simple Man",                 artist: "Lynyrd Skynyrd",           midiLow: 50, midiHigh: 63, genre: "Rock",         difficulty: "beginner" },
  { title: "Knockin' on Heaven's Door",  artist: "Bob Dylan",                midiLow: 47, midiHigh: 62, genre: "Rock",         difficulty: "beginner" },
  { title: "Lean on Me",                 artist: "Bill Withers",             midiLow: 48, midiHigh: 62, genre: "Soul",         difficulty: "beginner" },
  { title: "With or Without You",        artist: "U2",                       midiLow: 52, midiHigh: 64, genre: "Rock",         difficulty: "beginner" },
  { title: "Let Her Go",                 artist: "Passenger",                midiLow: 53, midiHigh: 65, genre: "Folk",         difficulty: "beginner" },
  { title: "Fast Car",                   artist: "Tracy Chapman",            midiLow: 50, midiHigh: 62, genre: "Folk",         difficulty: "beginner" },
  { title: "Blackbird",                  artist: "The Beatles",              midiLow: 55, midiHigh: 67, genre: "Rock",         difficulty: "beginner" },
  { title: "What a Wonderful World",     artist: "Louis Armstrong",          midiLow: 43, midiHigh: 57, genre: "Jazz",         difficulty: "beginner" },
  { title: "Eternal Flame",              artist: "The Bangles",              midiLow: 55, midiHigh: 67, genre: "Pop",          difficulty: "beginner" },
  { title: "Sweet Home Alabama",         artist: "Lynyrd Skynyrd",           midiLow: 48, midiHigh: 62, genre: "Rock",         difficulty: "beginner" },
  { title: "Man of Constant Sorrow",     artist: "Traditional",              midiLow: 45, midiHigh: 57, genre: "Folk",         difficulty: "beginner" },

  // ── Low range (bass/baritone) ────────────────────────────────────────────
  { title: "Ring of Fire",               artist: "Johnny Cash",              midiLow: 43, midiHigh: 60, genre: "Country",      difficulty: "intermediate" },
  { title: "Hallelujah",                 artist: "Leonard Cohen",            midiLow: 45, midiHigh: 62, genre: "Folk",         difficulty: "intermediate" },
  { title: "Can't Help Falling in Love", artist: "Elvis Presley",            midiLow: 47, midiHigh: 64, genre: "Pop",          difficulty: "beginner" },
  { title: "Stand By Me",                artist: "Ben E. King",              midiLow: 47, midiHigh: 62, genre: "Soul",         difficulty: "beginner" },
  { title: "House of the Rising Sun",    artist: "The Animals",              midiLow: 45, midiHigh: 65, genre: "Rock",         difficulty: "intermediate" },
  { title: "Unchained Melody",           artist: "The Righteous Brothers",   midiLow: 47, midiHigh: 67, genre: "Pop",          difficulty: "intermediate" },
  { title: "Hurt",                       artist: "Johnny Cash",              midiLow: 45, midiHigh: 60, genre: "Country",      difficulty: "beginner" },
  { title: "The Sound of Silence",       artist: "Simon & Garfunkel",        midiLow: 45, midiHigh: 64, genre: "Folk",         difficulty: "intermediate" },
  { title: "My Way",                     artist: "Frank Sinatra",            midiLow: 45, midiHigh: 65, genre: "Jazz",         difficulty: "intermediate" },
  { title: "Georgia on My Mind",         artist: "Ray Charles",              midiLow: 45, midiHigh: 65, genre: "Soul",         difficulty: "intermediate" },
  { title: "Summertime",                 artist: "Gershwin",                 midiLow: 48, midiHigh: 64, genre: "Jazz",         difficulty: "intermediate" },
  { title: "Everybody Hurts",            artist: "R.E.M.",                   midiLow: 48, midiHigh: 62, genre: "Rock",         difficulty: "beginner" },
  { title: "Across the Universe",        artist: "The Beatles",              midiLow: 47, midiHigh: 63, genre: "Rock",         difficulty: "beginner" },
  { title: "Tennessee Whiskey",          artist: "Chris Stapleton",          midiLow: 48, midiHigh: 65, genre: "Country",      difficulty: "intermediate" },

  // ── Mid range (baritone/tenor) ────────────────────────────────────────────
  { title: "Hey Jude",                   artist: "The Beatles",              midiLow: 50, midiHigh: 67, genre: "Rock",         difficulty: "intermediate" },
  { title: "Wonderwall",                 artist: "Oasis",                    midiLow: 50, midiHigh: 66, genre: "Rock",         difficulty: "beginner" },
  { title: "Let It Be",                  artist: "The Beatles",              midiLow: 48, midiHigh: 65, genre: "Rock",         difficulty: "beginner" },
  { title: "Thinking Out Loud",          artist: "Ed Sheeran",               midiLow: 50, midiHigh: 69, genre: "Pop",          difficulty: "intermediate" },
  { title: "Yesterday",                  artist: "The Beatles",              midiLow: 52, midiHigh: 67, genre: "Pop",          difficulty: "beginner" },
  { title: "Wish You Were Here",         artist: "Pink Floyd",               midiLow: 48, midiHigh: 64, genre: "Rock",         difficulty: "beginner" },
  { title: "Hotel California",           artist: "Eagles",                   midiLow: 50, midiHigh: 67, genre: "Rock",         difficulty: "intermediate" },
  { title: "Perfect",                    artist: "Ed Sheeran",               midiLow: 47, midiHigh: 67, genre: "Pop",          difficulty: "intermediate" },
  { title: "Someone Like You",           artist: "Adele",                    midiLow: 50, midiHigh: 68, genre: "Pop",          difficulty: "intermediate" },
  { title: "Mr. Brightside",             artist: "The Killers",              midiLow: 52, midiHigh: 68, genre: "Rock",         difficulty: "intermediate" },
  { title: "Africa",                     artist: "Toto",                     midiLow: 52, midiHigh: 67, genre: "Pop",          difficulty: "intermediate" },
  { title: "Don't Stop Believin'",       artist: "Journey",                  midiLow: 52, midiHigh: 71, genre: "Rock",         difficulty: "advanced" },
  { title: "Piano Man",                  artist: "Billy Joel",               midiLow: 50, midiHigh: 67, genre: "Pop",          difficulty: "intermediate" },
  { title: "Brown Eyed Girl",            artist: "Van Morrison",             midiLow: 50, midiHigh: 65, genre: "Rock",         difficulty: "beginner" },
  { title: "Sweet Caroline",             artist: "Neil Diamond",             midiLow: 52, midiHigh: 67, genre: "Pop",          difficulty: "beginner" },
  { title: "Stairway to Heaven",         artist: "Led Zeppelin",             midiLow: 52, midiHigh: 70, genre: "Rock",         difficulty: "advanced" },
  { title: "Under the Bridge",           artist: "Red Hot Chili Peppers",    midiLow: 50, midiHigh: 68, genre: "Rock",         difficulty: "intermediate" },
  { title: "Gravity",                    artist: "John Mayer",               midiLow: 52, midiHigh: 67, genre: "Blues",        difficulty: "intermediate" },
  { title: "Still of the Night",         artist: "Whitesnake",               midiLow: 50, midiHigh: 70, genre: "Rock",         difficulty: "advanced" },
  { title: "Come as You Are",            artist: "Nirvana",                  midiLow: 50, midiHigh: 65, genre: "Rock",         difficulty: "beginner" },
  { title: "Smells Like Teen Spirit",    artist: "Nirvana",                  midiLow: 50, midiHigh: 69, genre: "Rock",         difficulty: "intermediate" },
  { title: "Use Somebody",               artist: "Kings of Leon",            midiLow: 52, midiHigh: 70, genre: "Rock",         difficulty: "intermediate" },
  { title: "The Night We Met",           artist: "Lord Huron",               midiLow: 52, midiHigh: 65, genre: "Folk",         difficulty: "beginner" },
  { title: "To Make You Feel My Love",   artist: "Adele",                    midiLow: 50, midiHigh: 65, genre: "Pop",          difficulty: "beginner" },
  { title: "Shape of You",               artist: "Ed Sheeran",               midiLow: 53, midiHigh: 67, genre: "Pop",          difficulty: "intermediate" },
  { title: "The Scientist",              artist: "Coldplay",                 midiLow: 52, midiHigh: 67, genre: "Rock",         difficulty: "intermediate" },
  { title: "Fix You",                    artist: "Coldplay",                 midiLow: 52, midiHigh: 70, genre: "Rock",         difficulty: "intermediate" },
  { title: "Demons",                     artist: "Imagine Dragons",          midiLow: 53, midiHigh: 68, genre: "Pop",          difficulty: "beginner" },
  { title: "Radioactive",                artist: "Imagine Dragons",          midiLow: 50, midiHigh: 67, genre: "Pop",          difficulty: "intermediate" },
  { title: "Counting Stars",             artist: "OneRepublic",              midiLow: 52, midiHigh: 70, genre: "Pop",          difficulty: "intermediate" },
  { title: "Let Her Go",                 artist: "Passenger",                midiLow: 53, midiHigh: 65, genre: "Folk",         difficulty: "beginner" },
  { title: "Budapest",                   artist: "George Ezra",              midiLow: 47, midiHigh: 62, genre: "Folk",         difficulty: "beginner" },
  { title: "Barcelona",                  artist: "George Ezra",              midiLow: 47, midiHigh: 64, genre: "Folk",         difficulty: "beginner" },
  { title: "Ophelia",                    artist: "The Lumineers",            midiLow: 53, midiHigh: 68, genre: "Folk",         difficulty: "beginner" },
  { title: "Ho Hey",                     artist: "The Lumineers",            midiLow: 50, midiHigh: 65, genre: "Folk",         difficulty: "beginner" },
  { title: "Old Town Road",              artist: "Lil Nas X",                midiLow: 50, midiHigh: 65, genre: "Country",      difficulty: "beginner" },
  { title: "Jolene",                     artist: "Dolly Parton",             midiLow: 55, midiHigh: 74, genre: "Country",      difficulty: "advanced" },

  // ── Higher range (tenor/alto/mezzo) ───────────────────────────────────────
  { title: "Bohemian Rhapsody",          artist: "Queen",                    midiLow: 48, midiHigh: 76, genre: "Rock",         difficulty: "advanced" },
  { title: "Take Me to Church",          artist: "Hozier",                   midiLow: 50, midiHigh: 72, genre: "Alternative",  difficulty: "advanced" },
  { title: "Creep",                      artist: "Radiohead",                midiLow: 52, midiHigh: 72, genre: "Alternative",  difficulty: "advanced" },
  { title: "Shallow",                    artist: "Lady Gaga & Bradley Cooper", midiLow: 50, midiHigh: 74, genre: "Pop",        difficulty: "advanced" },
  { title: "Rolling in the Deep",        artist: "Adele",                    midiLow: 53, midiHigh: 74, genre: "Pop",          difficulty: "advanced" },
  { title: "I Will Always Love You",     artist: "Whitney Houston",          midiLow: 52, midiHigh: 77, genre: "Pop",          difficulty: "advanced" },
  { title: "Somewhere Over the Rainbow", artist: "Judy Garland",             midiLow: 55, midiHigh: 72, genre: "Pop",          difficulty: "intermediate" },
  { title: "At Last",                    artist: "Etta James",               midiLow: 50, midiHigh: 69, genre: "Soul",         difficulty: "intermediate" },
  { title: "Respect",                    artist: "Aretha Franklin",          midiLow: 53, midiHigh: 72, genre: "Soul",         difficulty: "intermediate" },
  { title: "Natural Woman",              artist: "Aretha Franklin",          midiLow: 52, midiHigh: 70, genre: "Soul",         difficulty: "intermediate" },
  { title: "Empire State of Mind",       artist: "Alicia Keys",              midiLow: 55, midiHigh: 72, genre: "R&B",          difficulty: "advanced" },
  { title: "If I Ain't Got You",         artist: "Alicia Keys",              midiLow: 52, midiHigh: 72, genre: "R&B",          difficulty: "advanced" },
  { title: "Halo",                       artist: "Beyoncé",                  midiLow: 55, midiHigh: 79, genre: "Pop",          difficulty: "advanced" },
  { title: "Crazy in Love",              artist: "Beyoncé",                  midiLow: 55, midiHigh: 74, genre: "R&B",          difficulty: "advanced" },
  { title: "Listen",                     artist: "Beyoncé",                  midiLow: 55, midiHigh: 76, genre: "R&B",          difficulty: "advanced" },
  { title: "Drunk in Love",              artist: "Beyoncé",                  midiLow: 50, midiHigh: 70, genre: "R&B",          difficulty: "intermediate" },
  { title: "No One",                     artist: "Alicia Keys",              midiLow: 55, midiHigh: 72, genre: "R&B",          difficulty: "intermediate" },
  { title: "Back to Black",              artist: "Amy Winehouse",            midiLow: 50, midiHigh: 68, genre: "Soul",         difficulty: "intermediate" },
  { title: "Rehab",                      artist: "Amy Winehouse",            midiLow: 52, midiHigh: 69, genre: "Soul",         difficulty: "intermediate" },
  { title: "Valerie",                    artist: "Amy Winehouse",            midiLow: 52, midiHigh: 69, genre: "Soul",         difficulty: "intermediate" },
  { title: "Hello",                      artist: "Adele",                    midiLow: 53, midiHigh: 72, genre: "Pop",          difficulty: "advanced" },
  { title: "Set Fire to the Rain",       artist: "Adele",                    midiLow: 55, midiHigh: 74, genre: "Pop",          difficulty: "advanced" },
  { title: "Skyfall",                    artist: "Adele",                    midiLow: 50, midiHigh: 72, genre: "Pop",          difficulty: "advanced" },
  { title: "Try",                        artist: "P!nk",                     midiLow: 52, midiHigh: 74, genre: "Pop",          difficulty: "advanced" },
  { title: "Just Give Me a Reason",      artist: "P!nk ft. Nate Ruess",      midiLow: 52, midiHigh: 72, genre: "Pop",          difficulty: "intermediate" },
  { title: "Landslide",                  artist: "Fleetwood Mac",            midiLow: 55, midiHigh: 70, genre: "Rock",         difficulty: "intermediate" },
  { title: "Dreams",                     artist: "Fleetwood Mac",            midiLow: 55, midiHigh: 70, genre: "Rock",         difficulty: "intermediate" },
  { title: "The Chain",                  artist: "Fleetwood Mac",            midiLow: 50, midiHigh: 68, genre: "Rock",         difficulty: "intermediate" },
  { title: "Wicked Game",                artist: "Chris Isaak",              midiLow: 48, midiHigh: 69, genre: "Rock",         difficulty: "intermediate" },
  { title: "Lovesong",                   artist: "The Cure",                 midiLow: 50, midiHigh: 66, genre: "Alternative",  difficulty: "beginner" },
  { title: "Mad World",                  artist: "Gary Jules",               midiLow: 52, midiHigh: 65, genre: "Alternative",  difficulty: "beginner" },
  { title: "Bittersweet Symphony",       artist: "The Verve",                midiLow: 52, midiHigh: 67, genre: "Alternative",  difficulty: "beginner" },
  { title: "Skinny Love",                artist: "Bon Iver",                 midiLow: 52, midiHigh: 70, genre: "Folk",         difficulty: "intermediate" },
  { title: "Holocene",                   artist: "Bon Iver",                 midiLow: 53, midiHigh: 72, genre: "Folk",         difficulty: "advanced" },
  { title: "Flume",                      artist: "Bon Iver",                 midiLow: 52, midiHigh: 68, genre: "Folk",         difficulty: "intermediate" },
  { title: "Ride",                       artist: "Twenty One Pilots",        midiLow: 52, midiHigh: 70, genre: "Alternative",  difficulty: "intermediate" },
  { title: "Stressed Out",               artist: "Twenty One Pilots",        midiLow: 55, midiHigh: 70, genre: "Alternative",  difficulty: "intermediate" },
  { title: "Heathens",                   artist: "Twenty One Pilots",        midiLow: 52, midiHigh: 70, genre: "Alternative",  difficulty: "intermediate" },
  { title: "Believer",                   artist: "Imagine Dragons",          midiLow: 52, midiHigh: 72, genre: "Pop",          difficulty: "intermediate" },
  { title: "Thunder",                    artist: "Imagine Dragons",          midiLow: 52, midiHigh: 71, genre: "Pop",          difficulty: "intermediate" },
  { title: "Blinding Lights",            artist: "The Weeknd",               midiLow: 53, midiHigh: 73, genre: "Pop",          difficulty: "intermediate" },
  { title: "Save Your Tears",            artist: "The Weeknd",               midiLow: 55, midiHigh: 73, genre: "Pop",          difficulty: "intermediate" },
  { title: "Can't Stop the Feeling",     artist: "Justin Timberlake",        midiLow: 55, midiHigh: 70, genre: "Pop",          difficulty: "intermediate" },
  { title: "Mirrors",                    artist: "Justin Timberlake",        midiLow: 52, midiHigh: 72, genre: "R&B",          difficulty: "intermediate" },
  { title: "Stay With Me",               artist: "Sam Smith",                midiLow: 53, midiHigh: 72, genre: "Pop",          difficulty: "intermediate" },
  { title: "Writing's on the Wall",      artist: "Sam Smith",                midiLow: 53, midiHigh: 76, genre: "Pop",          difficulty: "advanced" },
  { title: "Lose You to Love Me",        artist: "Selena Gomez",             midiLow: 55, midiHigh: 70, genre: "Pop",          difficulty: "intermediate" },
  { title: "Wolves",                     artist: "Selena Gomez",             midiLow: 55, midiHigh: 70, genre: "Pop",          difficulty: "beginner" },
  { title: "Flowers",                    artist: "Miley Cyrus",              midiLow: 55, midiHigh: 72, genre: "Pop",          difficulty: "intermediate" },
  { title: "Wrecking Ball",              artist: "Miley Cyrus",              midiLow: 55, midiHigh: 77, genre: "Pop",          difficulty: "advanced" },
  { title: "The Climb",                  artist: "Miley Cyrus",              midiLow: 55, midiHigh: 72, genre: "Pop",          difficulty: "intermediate" },
  { title: "Midnight Rain",              artist: "Taylor Swift",             midiLow: 53, midiHigh: 69, genre: "Pop",          difficulty: "intermediate" },
  { title: "All Too Well",               artist: "Taylor Swift",             midiLow: 55, midiHigh: 71, genre: "Pop",          difficulty: "intermediate" },
  { title: "Love Story",                 artist: "Taylor Swift",             midiLow: 55, midiHigh: 72, genre: "Country",      difficulty: "intermediate" },
  { title: "Don't Blame Me",             artist: "Taylor Swift",             midiLow: 55, midiHigh: 75, genre: "Pop",          difficulty: "advanced" },
  { title: "Shake It Off",               artist: "Taylor Swift",             midiLow: 55, midiHigh: 70, genre: "Pop",          difficulty: "beginner" },
  { title: "Cruel Summer",               artist: "Taylor Swift",             midiLow: 58, midiHigh: 74, genre: "Pop",          difficulty: "intermediate" },
  { title: "Levitating",                 artist: "Dua Lipa",                 midiLow: 55, midiHigh: 70, genre: "Pop",          difficulty: "beginner" },
  { title: "Don't Start Now",            artist: "Dua Lipa",                 midiLow: 55, midiHigh: 70, genre: "Pop",          difficulty: "intermediate" },
  { title: "Physical",                   artist: "Dua Lipa",                 midiLow: 55, midiHigh: 72, genre: "Pop",          difficulty: "intermediate" },
  { title: "Watermelon Sugar",           artist: "Harry Styles",             midiLow: 53, midiHigh: 69, genre: "Pop",          difficulty: "beginner" },
  { title: "As It Was",                  artist: "Harry Styles",             midiLow: 55, midiHigh: 70, genre: "Pop",          difficulty: "intermediate" },
  { title: "sign of the times",          artist: "Harry Styles",             midiLow: 55, midiHigh: 74, genre: "Rock",         difficulty: "advanced" },

  // ── High range (mezzo-soprano/soprano) ────────────────────────────────────
  { title: "Chandelier",                 artist: "Sia",                      midiLow: 55, midiHigh: 79, genre: "Pop",          difficulty: "advanced" },
  { title: "Elastic Heart",              artist: "Sia",                      midiLow: 55, midiHigh: 77, genre: "Pop",          difficulty: "advanced" },
  { title: "Cheap Thrills",              artist: "Sia",                      midiLow: 57, midiHigh: 72, genre: "Pop",          difficulty: "intermediate" },
  { title: "No Tears Left to Cry",       artist: "Ariana Grande",            midiLow: 58, midiHigh: 80, genre: "Pop",          difficulty: "advanced" },
  { title: "Thank U, Next",              artist: "Ariana Grande",            midiLow: 57, midiHigh: 76, genre: "Pop",          difficulty: "intermediate" },
  { title: "7 Rings",                    artist: "Ariana Grande",            midiLow: 57, midiHigh: 75, genre: "Pop",          difficulty: "intermediate" },
  { title: "Problem",                    artist: "Ariana Grande",            midiLow: 57, midiHigh: 77, genre: "Pop",          difficulty: "advanced" },
  { title: "Into You",                   artist: "Ariana Grande",            midiLow: 57, midiHigh: 77, genre: "Pop",          difficulty: "advanced" },
  { title: "Dangerous Woman",            artist: "Ariana Grande",            midiLow: 55, midiHigh: 79, genre: "Pop",          difficulty: "advanced" },
  { title: "Part of Your World",         artist: "The Little Mermaid",       midiLow: 55, midiHigh: 76, genre: "Pop",          difficulty: "advanced" },
  { title: "Let It Go",                  artist: "Frozen",                   midiLow: 60, midiHigh: 79, genre: "Pop",          difficulty: "advanced" },
  { title: "Colors of the Wind",         artist: "Pocahontas",               midiLow: 55, midiHigh: 76, genre: "Pop",          difficulty: "advanced" },
  { title: "Defying Gravity",            artist: "Wicked",                   midiLow: 55, midiHigh: 81, genre: "Musical",      difficulty: "advanced" },
  { title: "Memory",                     artist: "Cats",                     midiLow: 55, midiHigh: 76, genre: "Musical",      difficulty: "advanced" },
  { title: "On My Own",                  artist: "Les Misérables",           midiLow: 57, midiHigh: 76, genre: "Musical",      difficulty: "advanced" },
  { title: "The Power of Love",          artist: "Celine Dion",              midiLow: 55, midiHigh: 79, genre: "Pop",          difficulty: "advanced" },
  { title: "My Heart Will Go On",        artist: "Celine Dion",              midiLow: 55, midiHigh: 76, genre: "Pop",          difficulty: "advanced" },
  { title: "To Love You More",           artist: "Celine Dion",              midiLow: 55, midiHigh: 78, genre: "Pop",          difficulty: "advanced" },
  { title: "And I Am Telling You",       artist: "Dreamgirls",               midiLow: 55, midiHigh: 81, genre: "Musical",      difficulty: "advanced" },
  { title: "Queen of the Night",         artist: "The Magic Flute",          midiLow: 60, midiHigh: 84, genre: "Classical",    difficulty: "advanced" },

  // ── Blues / R&B / Soul ────────────────────────────────────────────────────
  { title: "The Thrill is Gone",         artist: "B.B. King",                midiLow: 47, midiHigh: 64, genre: "Blues",        difficulty: "intermediate" },
  { title: "Pride and Joy",              artist: "Stevie Ray Vaughan",       midiLow: 48, midiHigh: 64, genre: "Blues",        difficulty: "intermediate" },
  { title: "Red House",                  artist: "Jimi Hendrix",             midiLow: 48, midiHigh: 66, genre: "Blues",        difficulty: "intermediate" },
  { title: "Superstition",               artist: "Stevie Wonder",            midiLow: 50, midiHigh: 68, genre: "R&B",          difficulty: "intermediate" },
  { title: "Isn't She Lovely",           artist: "Stevie Wonder",            midiLow: 50, midiHigh: 67, genre: "R&B",          difficulty: "intermediate" },
  { title: "Higher Ground",              artist: "Stevie Wonder",            midiLow: 52, midiHigh: 69, genre: "R&B",          difficulty: "intermediate" },
  { title: "Ain't No Sunshine",          artist: "Bill Withers",             midiLow: 47, midiHigh: 62, genre: "Soul",         difficulty: "beginner" },
  { title: "Lovely Day",                 artist: "Bill Withers",             midiLow: 50, midiHigh: 79, genre: "Soul",         difficulty: "advanced" },
  { title: "Let's Stay Together",        artist: "Al Green",                 midiLow: 50, midiHigh: 69, genre: "Soul",         difficulty: "intermediate" },
  { title: "Let's Get It On",            artist: "Marvin Gaye",              midiLow: 52, midiHigh: 70, genre: "Soul",         difficulty: "intermediate" },
  { title: "What's Going On",            artist: "Marvin Gaye",              midiLow: 50, midiHigh: 67, genre: "Soul",         difficulty: "intermediate" },
  { title: "Sexual Healing",             artist: "Marvin Gaye",              midiLow: 48, midiHigh: 65, genre: "Soul",         difficulty: "beginner" },
  { title: "I Heard It Through the Grapevine", artist: "Marvin Gaye",       midiLow: 50, midiHigh: 68, genre: "Soul",         difficulty: "intermediate" },
  { title: "Purple Rain",                artist: "Prince",                   midiLow: 50, midiHigh: 72, genre: "R&B",          difficulty: "advanced" },
  { title: "Kiss",                       artist: "Prince",                   midiLow: 55, midiHigh: 79, genre: "R&B",          difficulty: "advanced" },
  { title: "When Doves Cry",             artist: "Prince",                   midiLow: 53, midiHigh: 72, genre: "R&B",          difficulty: "intermediate" },

  // ── Jazz ──────────────────────────────────────────────────────────────────
  { title: "Fly Me to the Moon",         artist: "Frank Sinatra",            midiLow: 47, midiHigh: 64, genre: "Jazz",         difficulty: "beginner" },
  { title: "The Way You Look Tonight",   artist: "Tony Bennett",             midiLow: 45, midiHigh: 64, genre: "Jazz",         difficulty: "beginner" },
  { title: "Autumn Leaves",              artist: "Eva Cassidy",              midiLow: 52, midiHigh: 69, genre: "Jazz",         difficulty: "intermediate" },
  { title: "Feeling Good",               artist: "Nina Simone",              midiLow: 48, midiHigh: 69, genre: "Jazz",         difficulty: "intermediate" },
  { title: "Misty",                      artist: "Erroll Garner",            midiLow: 50, midiHigh: 67, genre: "Jazz",         difficulty: "intermediate" },
  { title: "My Favorite Things",         artist: "John Coltrane",            midiLow: 55, midiHigh: 72, genre: "Jazz",         difficulty: "intermediate" },
  { title: "Cry Me a River",             artist: "Julie London",             midiLow: 50, midiHigh: 67, genre: "Jazz",         difficulty: "intermediate" },
  { title: "Dream a Little Dream",       artist: "Ella Fitzgerald",          midiLow: 52, midiHigh: 69, genre: "Jazz",         difficulty: "intermediate" },
  { title: "The Lady Is a Tramp",        artist: "Ella Fitzgerald",          midiLow: 52, midiHigh: 69, genre: "Jazz",         difficulty: "intermediate" },
  { title: "Blue Skies",                 artist: "Irving Berlin",            midiLow: 52, midiHigh: 67, genre: "Jazz",         difficulty: "beginner" },
];

// ── Scoring ─────────────────────────────────────────────────────────────────

function scoreSong(song, userMidiMin, userMidiMax) {
  const overlapLow = Math.max(song.midiLow, userMidiMin);
  const overlapHigh = Math.min(song.midiHigh, userMidiMax);
  const overlap = Math.max(0, overlapHigh - overlapLow);
  const songSpan = song.midiHigh - song.midiLow;
  if (songSpan <= 0) return 0;

  const coverage = overlap / songSpan;
  const overshootLow = Math.max(0, userMidiMin - song.midiLow);
  const overshootHigh = Math.max(0, song.midiHigh - userMidiMax);
  const overshootPenalty = (overshootLow + overshootHigh) / songSpan;

  return Math.max(0, coverage - overshootPenalty * 0.5);
}

// ── Filter config ───────────────────────────────────────────────────────────

const ALL_GENRES = [...new Set(SONG_DATABASE.map((s) => s.genre))].sort();
const DIFFICULTY_LABELS = { beginner: "Beginner", intermediate: "Intermediate", advanced: "Advanced" };

// ── Component ───────────────────────────────────────────────────────────────

function SongSuggestions({ results, maxSuggestions = 8 }) {
  const [genreFilter, setGenreFilter] = useState("All");
  const [difficultyFilter, setDifficultyFilter] = useState("All");

  const allSuggestions = useMemo(() => {
    const f0Min = results?.pitch?.f0_min ?? results?.summary?.f0_min;
    const f0Max = results?.pitch?.f0_max ?? results?.summary?.f0_max;

    if (!Number.isFinite(f0Min) || !Number.isFinite(f0Max)) return [];

    const userMidiMin = hzToMidi(f0Min);
    const userMidiMax = hzToMidi(f0Max);
    if (userMidiMin === null || userMidiMax === null) return [];

    return SONG_DATABASE
      .map((song) => ({ ...song, score: scoreSong(song, userMidiMin, userMidiMax) }))
      .filter((s) => s.score >= 0.55)
      .sort((a, b) => b.score - a.score);
  }, [results]);

  const suggestions = useMemo(() => {
    return allSuggestions
      .filter((s) => genreFilter === "All" || s.genre === genreFilter)
      .filter((s) => difficultyFilter === "All" || s.difficulty === difficultyFilter)
      .slice(0, maxSuggestions);
  }, [allSuggestions, genreFilter, difficultyFilter, maxSuggestions]);

  // What genres actually have matches for this singer?
  const availableGenres = useMemo(() => {
    const genres = new Set(allSuggestions.map((s) => s.genre));
    return ALL_GENRES.filter((g) => genres.has(g));
  }, [allSuggestions]);

  if (allSuggestions.length === 0) return null;

  return (
    <section className="song-suggestions" aria-label="Song suggestions based on your range">
      <h3 className="song-suggestions__title">Songs that fit your voice</h3>
      <p className="song-suggestions__subtitle">
        Based on your detected range. {allSuggestions.length} songs match — filter below.
      </p>

      {/* Filters */}
      <div className="song-suggestions__filters" role="group" aria-label="Filter songs">
        <div className="song-suggestions__filter-group">
          <label className="song-suggestions__filter-label" htmlFor="song-genre-filter">Genre</label>
          <select
            id="song-genre-filter"
            className="song-suggestions__filter-select"
            value={genreFilter}
            onChange={(e) => setGenreFilter(e.target.value)}
          >
            <option value="All">All genres</option>
            {availableGenres.map((g) => (
              <option key={g} value={g}>{g}</option>
            ))}
          </select>
        </div>
        <div className="song-suggestions__filter-group">
          <label className="song-suggestions__filter-label" htmlFor="song-difficulty-filter">Difficulty</label>
          <select
            id="song-difficulty-filter"
            className="song-suggestions__filter-select"
            value={difficultyFilter}
            onChange={(e) => setDifficultyFilter(e.target.value)}
          >
            <option value="All">All levels</option>
            {Object.entries(DIFFICULTY_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>
      </div>

      {suggestions.length === 0 ? (
        <p className="song-suggestions__empty">No songs match the current filters — try widening them.</p>
      ) : (
        <ul className="song-suggestions__list">
          {suggestions.map((song) => {
            const fitPct = Math.round(song.score * 100);
            return (
              <li key={`${song.title}-${song.artist}`} className="song-suggestions__item">
                <div className="song-suggestions__info">
                  <span className="song-suggestions__song-title">{song.title}</span>
                  <span className="song-suggestions__artist">{song.artist}</span>
                </div>
                <div className="song-suggestions__meta">
                  <span className="song-suggestions__genre">{song.genre}</span>
                  <span
                    className={`song-suggestions__difficulty song-suggestions__difficulty--${song.difficulty}`}
                  >
                    {DIFFICULTY_LABELS[song.difficulty]}
                  </span>
                  <span
                    className="song-suggestions__fit"
                    style={{ color: fitPct >= 90 ? "var(--success)" : fitPct >= 75 ? "#fbbf24" : "var(--text-muted)" }}
                  >
                    {fitPct}% fit
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export default SongSuggestions;
