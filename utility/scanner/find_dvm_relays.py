# scripts/find_dvm_relays.py - Search public relays to see if they have DVM data

import os
from pathlib import Path
import yaml
from tqdm import tqdm
from loguru import logger
import asyncio
from nostr_sdk import Client, Keys, Filter, Timestamp, Kind, Event, HandleNotification
import math
from typing import List, Dict, Any
import time
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from operator import itemgetter


RELAYS = [
    "relay.nostrdice.com",
    "nostr.1312.media",
    "45.135.180.104",
    "nostr.yael.at",
    "relay.nostr.net",
    "lunchbox.sandwich.farm",
    "nostr.dbtc.link",
    "nostr.sprovoost.nl",
    "nostr.myshosholoza.co.za",
    "travis-shears-nostr-relay-v2.fly.dev",
    "nostr.x0f.org",
    "nostr.stakey.net",
    "nostr.sebastix.dev",
    "relay.jellyfish.land",
    "nostr.at",
    "relay.varke.eu",
    "user.kindpag.es",
    "relay.hs.vc",
    "ae.purplerelay.com",
    "in.purplerelay.com",
    "ch.purplerelay.com",
    "history.nostr.watch",
    "wot.nostr.net",
    "relay.olas.app",
    "relay.highlighter.com",
    "me.purplerelay.com",
    "relay.nostrhub.fr",
    "de.purplerelay.com",
    "uk.purplerelay.com",
    "nostr.caramboo.com",
    "bitcoinmaximalists.online",
    "relay.nostrified.org",
    "nostr01.counterclockwise.io",
    "purplepag.es",
    "relay.nostr.lighting",
    "f7z.io",
    "privateisland.club",
    "nostr.einundzwanzig.space",
    "nostr4.daedaluslabs.io",
    "nostrum.satoshinakamoto.win",
    "nostr.1f52b.xyz",
    "nostr.oxtr.dev",
    "paid.nostrified.org",
    "relay.nsecbunker.com",
    "relay.weloveit.info",
    "wot.mwaters.net",
    "relay.arx-ccn.com",
    "relay.nostrview.com",
    "nostr.lu.ke",
    "nostr.cercatrova.me",
    "polnostr.xyz",
    "nostr.jonmartins.com",
    "relay.mwaters.net",
    "relay.stoner.com",
    "knostr.neutrine.com",
    "nostr.swiss-enigma.ch",
    "nostr.lopp.social",
    "nostr.polonkai.eu",
    "wot.nostr.sats4.life",
    "wot.shaving.kiwi",
    "wot.dtonon.com",
    "ir.purplerelay.com",
    "nostr.tavux.tech",
    "private.red.gb.net",
    "purplerelay.com",
    "soloco.nl",
    "pyramid.fiatjaf.com",
    "eu.purplerelay.com",
    "fl.purplerelay.com",
    "nostr-pr04.redscrypt.org",
    "nostr-pub.wellorder.net",
    "relay.wellorder.net",
    "nostr2.sanhauf.com",
    "relay.camelus.app",
    "relay.freeplace.nl",
    "nostr.chaima.info",
    "relay.utih.net",
    "nostr.openhoofd.nl",
    "nostr.sathoarder.com",
    "a.nos.lol",
    "nostr.daedaluslabs.io",
    "njump.me",
    "nostr.dumango.com",
    "nostr.hashbang.nl",
    "relay.badgr.digital",
    "nostr.mom",
    "nos.lol",
    "e.nos.lol",
    "nostr.koning-degraaf.nl",
    "nostr.sidnlabs.nl",
    "nostr.l00p.org",
    "nostr2.daedaluslabs.io",
    "obiurgator.thewhall.com",
    "nostr.madco.me",
    "h.codingarena.top/inbox",
    "nostr.karmickoala.info",
    "nostr.blockpower.capital",
    "relay.snort.social",
    "relay.nostr.bg",
    "nostr.ingwie.me",
    "strfry.openhoofd.nl",
    "wot.nostr.party",
    "labour.fiatjaf.com",
    "wot.codingarena.top",
    "relay.botev.sv",
    "social.protest.net/relay",
    "immo.jellyfish.land",
    "relay.nostr.wf",
    "nostr.openordex.org",
    "nr.rosano.ca",
    "cfrelay.royalgarter.workers.dev",
    "nostr.hifish.org",
    "nostr.dodge.me.uk",
    "relay.vengeful.eu",
    "nostr.cizmar.net",
    "relay.guggero.org",
    "nostr.0x7e.xyz",
    "orangesync.tech",
    "relay.customkeys.de",
    "relay.das.casa",
    "relay.xplbzx.uk",
    "premium.primal.net",
    "ditto.slothy.win/relay",
    "relay.nostr.jabber.ch",
    "at.nostrworks.com",
    "nostr1.daedaluslabs.io",
    "nostr.grooveix.com",
    "relay.8333.space",
    "relay.stens.dev",
    "nostr.agentcampfire.com",
    "fiatjaf.com",
    "nostr.self-determined.de",
    "haven.accioly.social",
    "nostr.256k1.dev",
    "relay.primal.net",
    "nostr.se7enz.com",
    "wot.azzamo.net",
    "nostr.pareto.space",
    "btcpay2.nisaba.solutions/nostr",
    "relay.shop21.dk",
    "nostrelay.memory-art.xyz",
    "relay.nostr.hach.re",
    "relay.orangepill.ovh",
    "relay.ingwie.me",
    "nostr.huszonegy.world",
    "nsrelay.assilvestrar.club",
    "relay.lumina.rocks",
    "relay2.angor.io",
    "relay.nostraddress.com",
    "untreu.me",
    "relay.stream.labs.h3.se",
    "tollbooth.stens.dev",
    "nostr.sats.li",
    "nostr.kolbers.de",
    "relay.nostrr.de",
    "custom.fiatjaf.com",
    "cfrelay.snowcait.workers.dev",
    "relay.rkus.se",
    "nostr.vulpem.com",
    "nostr.noones.com",
    "relay.nostr.nu",
    "nostr.filmweb.pl",
    "relay.azzamo.net",
    "nostr.t-rg.ws",
    "ftp.halifax.rwth-aachen.de/nostr",
    "nostr.btc-library.com",
    "relay.verified-nostr.com",
    "nostr.hubmaker.io",
    "nostr.jfischer.org",
    "relay2.nostrasia.net",
    "nostr.azzamo.net",
    "relay.rengel.org",
    "nostr-relay.app",
    "echo.websocket.org",
    "nostr.kosmos.org",
    "relay.degmods.com",
    "nostr.ovia.to",
    "nostr-verif.slothy.win",
    "relay.dwadziesciajeden.pl",
    "relay.nsec.app",
    "nostr.cypherpunk.today",
    "relay.cyphernomad.com",
    "community.proxymana.net",
    "relay.nostromo.social",
    "relay.nostrplebs.com",
    "greensoul.space",
    "relay.test.nquiz.io",
    "relay.sigit.io",
    "adoringcardinal1.lnbits.com/nostrrelay/test-relay",
    "relay.dannymorabito.com/inbox",
    "eden.nostr.land",
    "puravida.nostr.land",
    "nostr.land",
    "nostr.bitcoinist.org",
    "orangepiller.org",
    "relaypag.es",
    "relay.oh-happy-day.xyz",
    "nostr.noderunners.network",
    "relay.shawnyeager.com/chat",
    "atlas.nostr.land",
    "relay.nostr.hu",
    "nostr.heliodex.cf",
    "nostr.ussenterprise.xyz",
    "relay.groups.nip29.com",
    "relay.dev.ntech.it",
    "relay.snotr.nl:49999",
    "nostr.reelnetwork.eu",
    "nostr.javi.space",
    "xmr.ithurtswhenip.ee",
    "relay.nostrich.cc",
    "nostr.schorsch.fans",
    "nostr.heavyrubberslave.com",
    "nostr.manasiwibi.com",
    "nostr.mikoshi.de",
    "promenade.fiatjaf.com",
    "team-relay.pareto.space",
    "null.spdns.eu",
    "nostr.slothy.win",
    "nostr.data.haus",
    "relay.nostrcheck.me",
    "nostr.strits.dk",
    "nostr.thurk.org",
    "relay.alex71btc.com",
    "nostr.mtrj.cz",
    "nostr-pr03.redscrypt.org",
    "nostr.phuture.sk",
    "relay.moinsen.com",
    "v1250.planz.io/nostr",
    "notes.miguelalmodo.com",
    "nostr.petrkr.net/strfry",
    "relay.fanfares.io",
    "chronicle.dev.ntech.it",
    "nostr.pipegrep.se:2121",
    "fido-news.z7.ai",
    "relay.noderunners.network",
    "rebelbase.social/relay",
    "chronicle.puhcho.me",
    "nostr.rosenbaum.se",
    "haven.puhcho.me",
    "relay.chakany.systems",
    "kitchen.zap.cooking",
    "relay.zone667.com",
    "node.coincreek.com/nostrclient/api/v1/relay",
    "multiplexer.huszonegy.world",
    "relay.s-w.art",
    "mailbox.mw.leastauthority.com/v1",
    "nostr.neilalexander.dev",
    "relay.agorist.space",
    "relay.despera.space",
    "groups.fiatjaf.com",
    "nostr.satstralia.com",
    "wot.sovbit.host",
    "relay.minibits.cash",
    "relay.piazza.today",
    "relay2.nostrchat.io",
    "nostr.rikmeijer.nl",
    "nostria.space",
    "cfrelay.puhcho.workers.dev",
    "relay.ryzizub.com",
    "hist.nostr.land",
    "freelay.sovbit.host",
    "nip85.nostr.band",
    "relay.bitcoinveneto.org",
    "nproxy.kristapsk.lv",
    "relay.nostronautti.fi",
    "nostrua.com",
    "czas.live",
    "relay.minibolt.info",
    "nostr.schneimi.de",
    "social.proxymana.net",
    "relay.nostr.band",
    "nostr.gleeze.com",
    "relay.netstr.io",
    "feeds.nostr.band/nostrhispano",
    "adre.su",
    "nostr.holbrook.no",
    "relay.tv-base.com",
    "nostr2.azzamo.net",
    "nostr-pr02.redscrypt.org",
    "xmr.usenostr.org",
    "no.netsec.vip",
    "lolicon.monster",
    "inbox.azzamo.net",
    "nostr.plantroon.com",
    "nostr.sovbit.host",
    "nostr.d11n.net",
    "relay.gasteazi.net",
    "nostr.rblb.it:7777",
    "nostr.wine",
    "nostr.inosta.cc",
    "relay.getalby.com/v1",
    "bnc.netsec.vip",
    "ghost.dolu.dev",
    "btc.klendazu.com",
    "relay.fountain.fm",
    "cache2.primal.net/v1",
    "cache1.primal.net/v1",
    "nostr.thank.eu",
    "nostr.spaceshell.xyz",
    "unostr.site",
    "nostr.namek.link",
    "nosflare.plebes.fans",
    "prl.plus",
    "relay.crbl.io",
    "nostr.portemonero.com",
    "nostr.lifeonbtc.xyz",
    "nostr-relay.sn-media.com",
    "nostr.jcloud.es",
    "relay.hunstr.mywire.org",
    "nostr.lojong.info",
    "nostr.primz.org",
    "nostr.xmr.rocks",
    "misskey.social",
    "nostr.itdestro.cc",
    "strfry.iris.to",
    "mls.akdeniz.edu.tr/nostr",
    "sendit.nosflare.com",
    "relay.transtoad.com",
    "news.nos.social",
    "nostr.8777.ch",
    "nostr.searx.is",
    "relay1.nostrchat.io",
    "bostr.bitcointxoko.com",
    "relay-nwc.rizful.com/v1",
    "devs.nostr1.com",
    "thebarn.nostr1.com",
    "brb.io",
    "alru07.nostr1.com",
    "rocky.nostr1.com",
    "reimagine.nostr1.com",
    "zaplab.nostr1.com",
    "relay.notestack.com",
    "sources.nostr1.com",
    "relay.nostrfreedom.net/outbox",
    "nostr.takasaki.dev",
    "pareto.nostr1.com",
    "support.nostr1.com",
    "libretechsystems.nostr1.com",
    "slick.mjex.me",
    "relay.nostrify.io",
    "zorrelay.libretechsystems.xyz",
    "fabian.nostr1.com",
    "nostrue.com",
    "nostr.rubberdoll.cc",
    "relay.usefusion.ai",
    "cyberspace.nostr1.com",
    "social.olsentribe.fyi",
    "christpill.nostr1.com",
    "relay.mostro.network",
    "dikaios1517.nostr1.com",
    "hax.reliefcloud.com",
    "schnorr.me",
    "wbc.nostr1.com",
    "hivetalk.nostr1.com",
    "rly.bopln.com",
    "relay.jerseyplebs.com",
    "cobrafuma.com/relay",
    "relay.angor.io",
    "wot.relay.vanderwarker.family",
    "basedpotato.nostr1.com",
    "primus.nostr1.com",
    "rly.nostrkid.com",
    "nostr.atitlan.io",
    "relay.nostriot.com",
    "vitor.nostr1.com",
    "relay.satlantis.io",
    "relay.artx.market",
    "zap.watch",
    "nostrrelay.taylorperron.com",
    "relay.noswhere.com",
    "nostr.polyserv.xyz",
    "nostr.red5d.dev",
    "nostr.d3id.xyz/relay",
    "relay.vanderwarker.family",
    "rkgk.moe",
    "strfry.orange-crush.com",
    "relay.flirtingwithbitcoin.com",
    "relay.chrisatmachine.com",
    "relay.nostrarabia.com",
    "relay.hamnet.io",
    "theforest.nostr1.com",
    "relay.devstr.org",
    "frjosh.nostr1.com",
    "nostr.dakukitsune.ca",
    "relay.utxo.one",
    "relay.oke.minds.io/nostr/v1/ws",
    "fiatjaf.nostr1.com",
    "bots.utxo.one",
    "nostr.zbd.gg",
    "wot.utxo.one",
    "dwebcamp.nos.social",
    "mleku.realy.lol",
    "nostr.mining.sc",
    "relay.bitcoinpark.com",
    "frens.nostr1.com",
    "news.utxo.one",
    "nostr.roundrockbitcoiners.com",
    "relay.kamp.site",
    "nostr.timegate.co",
    "relay.devs.tools",
    "riley.timegate.co",
    "willow.timegate.co",
    "relay.devvul.com",
    "nostr.nodeofsven.com",
    "relay.s3x.social",
    "nostr.cloud.vinney.xyz",
    "nostr2.girino.org",
    "strfry.shock.network",
    "nostr-rs-relay.dev.fedibtc.com",
    "nip13.girino.org",
    "relay.tagayasu.xyz",
    "nostrelites.org",
    "relay.geyser.fund",
    "nostr.gerbils.online",
    "nostr.girino.org",
    "relay.sebdev.io",
    "nostr-dev.zbd.gg",
    "nostr.coincrowd.fund",
    "lnbits.satoshibox.io/nostrclient/api/v1/relay",
    "relay.nos.social",
    "relay.staging.geyser.fund",
    "ragnar-relay.com",
    "nostr.drafted.pro",
    "nostr.2h2o.io",
    "relay.orange-crush.com",
    "relay.nostr.sc",
    "gleasonator.dev/relay",
    "nostr.mdip.yourself.dev",
    "relay.gnostr.cloud",
    "relay.openbalance.app",
    "nostr.topeth.info",
    "21ideas.nostr1.com",
    "pay.thefockinfury.wtf/nostrrelay/1",
    "straylight.cafe/relay",
    "bitcoiner.social",
    "dev-relay.kube.b-n.space",
    "nostr.novacisko.cz",
    "relay.wavlake.com",
    "relay.mattybs.lol",
    "haven.tealeaf.dev/inbox",
    "relay.patrickulrich.com/inbox",
    "relay.lexingtonbitcoin.org",
    "yestr.me",
    "slime.church/relay",
    "wot.tealeaf.dev",
    "relay.minds.com/nostr/v1/ws",
    "eclipse.pub/relay",
    "nostr21.com",
    "lightningrelay.com",
    "relay.nostr.ai",
    "relay.livefreebtc.dev",
    "dtonon.nostr1.com",
    "relay.goodmorningbitcoin.com",
    "freespeech.casa",
    "us.purplerelay.com",
    "nostr.pailakapo.com",
    "memrelay.girino.org",
    "mastodon.cloud/api/v1/streaming",
    "nostr.happytavern.co",
    "chorus.tealeaf.dev",
    "relay.tapestry.ninja",
    "nostr.thebiglake.org",
    "strfry.chatbett.de",
    "ca.purplerelay.com",
    "haven.cyberhornet.net",
    "relay.newatlantis.top",
    "wot.zacoos.com",
    "hodlbod.coracle.tools",
    "relay.arrakis.lat",
    "wot.girino.org",
    "relay.magiccity.live",
    "wot.sandwich.farm",
    "brisceaux.com",
    "relay.illuminodes.com",
    "relay.btcforplebs.com",
    "relay.oldcity-bitcoiners.info",
    "relay.roygbiv.guide",
    "relay.farscapian.com",
    "nostr.notribe.net",
    "relay.corpum.com",
    "merrcurrup.railway.app",
    "nostr.community.ath.cx",
    "haven.ciori.net",
    "relay.mostr.pub",
    "relay.nostrtalk.org",
    "ditto.openbalance.app/relay",
    "bonifatius.nostr1.com",
    "nostr.phauna.org",
    "nostr.liberty.fans",
    "wot.sebastix.social",
    "henhouse.social/relay",
    "us.nostr.wine",
    "wheat.happytavern.co",
    "haven.nostrver.se",
    "bitstack.app",
    "relay.isphere.lol",
    "auth.nostr1.com",
    "inner.sebastix.social",
    "logen.btcforplebs.com",
    "bevo.nostr1.com",
    "nostr-news.nostr1.com",
    "nostrich.zonemix.tech",
    "nostr-relay.derekross.me",
    "nostr.overmind.lol",
    "relay.notmandatory.org",
    "frysian.nostrich.casa",
    "monitorlizard.nostr1.com",
    "relay.damus.io",
    "profiles.nostr1.com",
    "relay.cosmicbolt.net",
    "plebone.nostr1.com",
    "thecitadel.nostr1.com",
    "nostr-relay.philipcristiano.com",
    "offchain.pub",
    "relay5.bitransfer.org",
    "seth.nostr1.com",
    "relay.geektank.ai",
    "mandidraws.nostrnaut.love",
    "kirpy.nostrnaut.love",
    "nostr.tac.lol",
    "hotrightnow.nostr1.com",
    "filter.weme.wtf",
    "art.nostrfreaks.com",
    "thebarn.nostrfreaks.com",
    "relay.nostrfreaks.com",
    "wot.innovativecerebrum.ai",
    "relay.asthroughfire.com",
    "relay1.xfire.to:",
    "relay.nostrpunk.com",
    "strfry.bonsai.com",
    "anon.computer",
    "sorrelay.libretechsystems.xyz",
    "relay.pleb.to",
    "strfry.corebreach.com",
    "relay.poster.place",
    "relay.unknown.cloud",
    "tamby.mjex.me",
    "creatr.nostr.wine",
    "dergigi.nostr1.com",
    "nostr-rs-relay-ishosta.phamthanh.me",
    "welcome.nostr.wine",
    "relay.satoshidnc.com",
    "aplaceinthesun.nostr1.com",
    "relay.sovereign.app",
    "thewildhustle.nostr1.com",
    "relay.nuts.cash",
    "nostr.ch3n2k.com",
    "tigs.nostr1.com",
    "relay.coinos.io",
    "jingle.carlos-cdb.top",
    "nostr.animeomake.com",
    "nostr-1.nbo.angani.co",
    "nostril.cam",
    "nostr.fort-btc.club",
    "cellar.nostr.wine",
    "nostr.pjv.me",
    "bucket.coracle.social",
    "algo.utxo.one",
    "frens.utxo.one",
    "chorus.pjv.me",
    "nostr.psychoet.nexus",
    "us.nostr.land",
    "carlos-cdb.top",
    "onlynotes.lol",
    "relay.nostr-labs.xyz",
    "nostr.cltrrd.us",
    "articles.layer3.news",
    "nostr.sagaciousd.com",
    "adeptus.cwharton.com",
    "nostr-02.yakihonne.com",
    "rl.baud.one",
    "inbox.nostr-labs.xyz",
    "nostr.iz5wga.radio",
    "nostr.corebreach.com",
    "nostr-01.yakihonne.com",
    "nostr1.jpegslangah.com",
    "relay.westernbtc.com",
    "nostrelay.yeghro.com",
    "relays.diggoo.com",
    "asia.azzamo.net",
    "wot.siamstr.com",
    "nostr.tools.global.id",
    "satsage.xyz",
    "nostr.sectiontwo.org",
    "chorus.bonsai.com",
    "haven.calva.dev/inbox",
    "nostr.2b9t.xyz",
    "nostr-relay.psfoundation.info",
    "nostr.itsnebula.net",
    "nostr-02.dorafactory.org",
    "hi.myvoiceourstory.org",
    "relay.nostrology.org",
    "wons.calva.dev",
    "relay.benthecarman.com",
    "relay.gems.xyz",
    "nostr.skitso.business",
    "stg.nostpy.lol",
    "n.wingu.se",
    "nostrelay.yeghro.site",
    "nostr.semisol.dev",
    "nostr.hekster.org",
    "relay.unsupervised.online",
    "nostr-relay.bitcoin.ninja",
    "nostr.extrabits.io",
    "nostr.reckless.dev",
    "nostr.1sat.org",
    "relay.nostr.watch",
    "nostr.bilthon.dev",
    "relay.nostpy.lol",
    "elites.nostrati.org",
    "niel.nostr1.com",
    "hub.nostr-relay.app",
    "relay.nostrainsley.coracle.tools",
    "antisocial.nostr1.com",
    "wostr.hexhex.online",
    "nostr-relay.algotech.io",
    "wot.eminence.gdn",
    "thewritingdesk.nostr1.com",
    "haven.eternal.gdn",
    "lnbits.papersats.io/nostrclient/api/v1/relay",
    "jmoose.rocks",
    "relay.sovereign-stack.org",
    "relay.brightbolt.net/inbox",
    "agentorange.nostr1.com",
    "nostr.bitpunk.fm",
    "tijl.xyz",
    "relay.chontit.win",
    "nostr.jaonoctus.dev",
    "david.nostr1.com",
    "relay.maiqr.app",
    "nostr.rezhajulio.id",
    "relay.13room.space",
    "relay.lightning.gdn",
    "nostr-relay.schnitzel.world",
    "nostr.orangepill.dev",
    "relay.orangepill.dev",
    "relay.siamstr.com",
    "sushi.ski",
    "nostr.linke.de",
    "nostr.dlsouza.lol",
    "nostr.cottongin.xyz",
    "relay.notoshi.win",
    "relay-testnet.k8s.layer3.news",
    "nostr.hexhex.online",
    "bostr.lightningspore.com",
    "loli.church",
    "relay.lnfi.network",
    "nostr.easydns.ca",
    "relay.lawallet.ar",
    "relay.nostrcn.com",
    "nostr.babyshark.win",
    "relap.orzv.workers.dev",
    "bostr.nokotaro.work",
    "nortis.nostr1.com",
    "search.nos.today",
    "staging.yabu.me",
    "relay.stewlab.win",
    "nostr.dl3.dedyn.io",
    "haven.girino.org",
    "relay.beta.fogtype.com",
    "relay.hodl.ar",
    "nostrvista.aaroniumii.com",
    "relay.johnnyasantos.com",
    "nostr-03.dorafactory.org",
    "relay.axeldolce.xyz",
    "stratum.libretechsystems.xyz",
    "nostr.pistaum.com",
    "bostr.nokotaro.com",
    "novoa.nagoya",
    "srtrelay.c-stellar.net",
    "relay.lem0n.cc",
    "yabu.me",
    "nrelay.c-stellar.net",
    "nostr.tbai.me:592",
    "fiatrevelation.nostr1.com",
    "nosdrive.app/relay",
    "eupo43gj24.execute-api.us-east-1.amazonaws.com/test",
    "nostrja-kari.heguro.com",
    "nostr.kloudcover.com",
    "mats-techno-gnome-ca.trycloudflare.com",
    "rsslay.ch3n2k.com",
    "nostr.brackrat.com",
    "n3r.xyz",
    "relay.0v0.social",
    "junxingwang.org",
    "relay.zhoushen929.com",
    "nostr.camalolo.com",
    "au.purplerelay.com",
    "misskey.gothloli.club",
    "bostr.online",
    "magic.nostr1.com",
    "relay.momostr.pink",
    "brightlights.nostr1.com",
    "jp.purplerelay.com",
    "bostr.syobon.net",
    "tw.purplerelay.com",
    "hk.purplerelay.com",
    "nostr.me/relay",
    "nostr.15b.blue",
    "nostr.bitcoinvn.io",
    "kr.purplerelay.com",
    "airchat.nostr1.com",
    "relay.rodbishop.nz/inbox",
    "nostr.zoel.network",
    "proxy0.siamstr.com",
    "nostrrelay.win",
    "nerostr.girino.org",
    "relay.nostr.com.au",
    "relay.nostr.wirednet.jp",
    "devapi.freefrom.space/v1/ws",
    "n.ok0.org",
    "satellite.hzrd149.com",
    "kiwibuilders.nostr21.net",
    "ursin.nostr1.com",
    "api.freefrom.space/v1/ws",
    "relay-proxy.freefrom.club/v1/ws",
    "relay.lax1dude.net",
    "aaa-api.freefrom.space/v1/ws",
    "relay.casualcrypto.date",
    "relay29.notoshi.win",
    "nostr.middling.mydns.jp",
    "dev-relay.lnfi.network",
    "relay.bitdevs.tw",
    "moonboi.nostrfreaks.com",
    "kadargo.zw.is",
    "nostr.faust.duckdns.org",
    "nostr.btczh.tw",
    "nostr.tegila.com.br",
    "directory.yabu.me",
    "prod.mosavi.io/v1/ws",
    "hayloo.nostr1.com",
    "nostr-relay.cbrx.io",
    "stage.mosavi.io/v1/ws",
    "inbox.nostr.wine",
    "testnet.plebnet.dev/nostrrelay/1",
    "bostr.erechorse.com",
    "relay02.lnfi.network",
    "nostrich.adagio.tw",
    "nostr.stupleb.cc",
    "unhostedwallet.com",
    "groups.0xchat.com",
    "jingle.nostrver.se",
    "misskey.systems",
    "multiplextr.coracle.social",
    "relay.nostrid.com",
    "nfrelay.app",
    "backup.keychat.io",
    "relay.bostr.online",
    "nostr.hashi.sbs",
    "relay.shuymn.me",
    "wc1.current.ninja",
    "relay.refinery.coracle.tools",
    "relay.keychat.io",
    "nostr.dmgd.monster",
    "cfrelay.haorendashu.workers.dev",
    "relay.nostrdam.com",
    "nostr.ginuerzh.xyz",
    "nostr.intrepid18.com",
    "misskey.04.si",
    "relay.xeble.me",
    "powrelay.xyz",
    "relay.braydon.com",
    "misskey.takehi.to",
    "mleku.nostr1.com",
    "submarin.online",
    "core.btcmap.org/nostrrelay/relay",
    "relay.lifpay.me",
    "premis.one",
    "stage.mosavi.xyz/v1/ws",
    "9yo.punipoka.pink",
    "nostr.sats.coffee",
    "nostr.trepechov.com",
    "nostrja-kari-nip50.heguro.com",
    "invillage-outvillage.com",
    "misskey.art",
    "social.camph.net",
    "test.nfrelay.app",
    "eostagram.com",
    "nostrrelay.blocktree.cc",
    "misskey.cloud",
    "cl4.tnix.dev",
    "misskey.io",
    "misskey.design",
    "nr.yay.so",
    "osrs.nostr-labs.xyz",
    "problematic.network",
    "relay.nostar.org",
    "darknights.nostr1.com",
    "nostr.a2x.pub",
    "nostr-dev.wellorder.net",
    "nostr-verified.wellorder.net",
    "gnost.faust.duckdns.org",
    "nostr.synalysis.com",
    "ithurtswhenip.ee",
    "bostr.cx.ms",
    "nostr.cxplay.org",
    "relay.cxplay.org",
    "relay.utxo.one/private",
    "nostr.sats.coffee/",
    "quotes.mycelium.social/",
    "nostr.cizmar.net/",
    "free.relayted.de/",
    "nostr.felixzieger.de/",
    "nas.yunierrodriguez.com:4848/",
    "hayloo.nostr1.com/",
    "wot.brightbolt.net/",
    "nostr.self-determined.de/",
    "thebarn.nostr1.com/",
    "bostr.syobon.net/",
    "nostr.pailakapo.com/",
    "nostr.thebiglake.org/",
    "brightlights.nostr1.com/",
    "gitcitadel.nostr1.com/",
    "nostrue.com/",
    "nostr.myshosholoza.co.za/",
    "relay1.nostrchat.io/",
    "strfry.chatbett.de/",
    "relay.mostard.org/",
    "relay.mattybs.lol/",
    "relay.asthroughfire.com/",
    "rebelbase.social/relay",
    "airchat.nostr1.com/",
    "relay.sigit.io/",
    "slick.mjex.me/",
    "relay.nbswozlfpjuwc4y.boo/",
    "chronicle.ziomc.com/",
    "jskitty.cat/nostr",
    "relay.utih.net/",
    "social.camph.net/",
    "multiplextr.coracle.social/",
    "logstr.mycelium.social/",
    "inbox.mycelium.social/",
    "gnost.faust.duckdns.org/",
    "relay-fenrir.nexterz-sv.xyz/",
    "relay.j35tr.com/",
    "nostr.dlsouza.lol/",
    "freespeech.casa/",
    "zaplab.nostr1.com/",
    "nostr.bch.ninja/",
    "nostr.sovbit.host/",
    "nostrja-kari-http.heguro.com/",
    "nostr.xmr.rocks/",
    "bitcr-cloud-run-03-550030097098.europe",
    "relay.caramboo.com/",
    "relay.nostrhub.fr/",
    "merrcurrup.railway.app/",
    "nostr.notribe.net/",
    "relay.hodl.ar/",
    "wot.tealeaf.dev/",
    "nostr.2h2o.io/",
    "lightningrelay.com/",
    "nostr.walletofsatoshi.com/",
    "fabian.nostr1.com/",
    "nostr1.thelifeofanegro.com/",
    "nostr.portemonero.com/",
    "nostr.czas.plus/",
    "nostr.zoel.network/",
    "relay.minibolt.info/",
    "wot.eminence.gdn/",
    "welcome.nostr.wine/",
    "relay.nquiz.io/",
    "nostr.sathoarder.com/",
    "nostrapps.com/",
    "haven.on4r.net/inbox",
    "nostr.openordex.org/",
    "relay03.lnfi.network/",
    "community.proxymana.net/",
    "zap.watch/",
    "nostr.tools.global.id/",
    "relay.arrakis.lat/",
    "milwaukietalkie.nostr1.com/",
    "relay.geekiam.services/",
    "nostr.mining.sc/",
    "ursin.nostr1.com/",
    "nostr.mom/2123/416576/",
    "nostr.cottongin.xyz/",
    "rocky.nostr1.com/",
    "relay.exit.pub/",
    "relays.land/codytest",
    "pyramid.fiatjaf.com/",
    "yarnlady.21mil.me/",
    "kadargo.zw.is/",
    "pnostr.self-determined.de/inbox",
    "relay.kamp.site/",
    "relay.devvul.com/",
    "relay.mostro.network/",
    "relay.agorist.space/",
    "relay.rkus.se/",
    "linode.progserver.site:4848/",
    "relay.stream.labs.h3.se/",
    "chatwith.krisconstable.com/",
    "nostr.bilthon.dev/",
    "relay.oke.minds.io/nostr/v1/ws",
    "cfrelay.snowcait.workers.dev/",
    "nostr.jonmartins.com/",
    "nostr.256k1.dev/",
    "nostr.0x7e.xyz/",
    "wons.calva.dev/",
    "nostr.sebastix.dev/",
    "custom.fiatjaf.com/",
    "bitcoinmaximalists.online/",
    "staging.bitcointxoko.com/",
    "relay.utxo.one/chat",
    "mleku.nostr1.com/",
    "aegis.relaynostr.xyz/",
    "relay.sepiropht.me/",
    "nostr.chaima.info/",
    "primus.nostr1.com/",
    "dtonon.nostr1.com/",
    "fido-news.z7.ai/",
    "nostr.searx.is/",
    "news.nos.social/",
    "relay.nostromo.social/",
    "relay.evanverma.com/",
    "groups.0xchat.com/",
    "nostr-news.nostr1.com/",
    "nostr.fort-btc.club/",
    "relay.zapstore.dev/",
    "node-ior.webhop.me:4848/",
    "mar101xy.com/relay",
    "nostr.jfischer.org/",
    "relay.oh-happy-day.xyz/",
    "nostr.intrepid18.com/",
    "relay.magiccity.live/",
    "cc3d.nostr1.com/",
    "nostr21.com/",
    "relay.angor.io/",
    "nostr-news.nostr1.com/",
    "nostr.fort-btc.club/",
    "relay.zapstore.dev/",
    "node-ior.webhop.me:4848/",
    "mar101xy.com/relay",
    "nostr.jfischer.org/",
    "relay.oh-happy-day.xyz/",
    "nostr.intrepid18.com/",
    "relay.magiccity.live/",
    "cc3d.nostr1.com/",
    "nostr21.com/",
    "relay.angor.io/",
    "relay.olas.app/",
    "jklksdnbit.duckdns.org:3355/",
    "relay.kreweofkeys.net/",
    "relay.yana.do/",
    "me.purplerelay.com/",
    "ir.purplerelay.com/",
    "relay.nostrview.com/",
    "relay.cyphernomad.com/",
    "h.codingarena.top/inbox",
    "202.61.207.49:8090/",
    "haven.tealeaf.dev/",
    "relay.wikifreedia.xyz/",
    "nostr.btc-library.com/",
    "194.195.222.47:4848/",
    "monitorlizard.nostr1.com/",
    "nostr-rs-relay.dev.fedibtc.com/",
    "relay.westernbtc.com/",
    "hbr.coracle.social/",
    "nostr.atitlan.io/",
    "nostr.azzamo.net/",
    "relay.shop21.dk/",
    "nostr.dodge.me.uk/",
    "nostr.messagepush.io/",
    "hk.purplerelay.com/",
    "nip85.nostr.band/",
    "jingle.nostrver.se/",
    "feeds.nostr.band/typescript",
    "relay.bitcoinveneto.org/",
    "relay.nostr.net/",
    "nr.rosano.ca/",
    "au.purplerelay.com/",
    "relay.siamstr.com/",
    "rsslay.ch3n2k.com/",
    "relay.nostpy.lol/",
    "relay.lumina.rocks/",
    "nostr.pareto.space/",
    "nostr.ussenterprise.xyz/",
    "misskey.io/",
    "nostr.hashi.sbs/",
    "relay.mess.ch/",
    "bostr.syobon.net/",
    "strfry.bonsai.com/",
    "haven.ciori.net/",
    "relay.chontit.win/",
    "relay.openbalance.app/",
    "nostr.skitso.business/",
    "relay.illuminodes.com/",
    "relay.stewlab.win/",
    "relay.xeble.me/",
    "relay.nostr.ai/",
    "nostream-production-643a.up.railway.app/",
    "nostr.bitcoinist.org/",
    "nostr.commonshub.brussels/",
    "orangepiller.org/",
    "wot.brightbolt.net/",
    "chorus.bonsai.com/",
    "nostr-dev.zbd.gg/",
    "nostr.gleeze.com/",
    "relay.nostrfreedom.net/inbox",
    "relay.757btc.org/",
    "nostr.yael.at/",
    "xmr.usenostr.org/",
    "nostr.rtvslawenia.com/",
    "relay.nostr.wf/",
    "relay.mostr.pub/",
    "relay.corpum.com/",
    "relay.lightning.gdn/",
    "nostr.lorentz.is/",
    "nostr.gerbils.online/",
    "relay.noderunners.network/invoices",
    "relay.nostr.nu/",
    "ithurtswhenip.ee/",
    "social.protest.net/relay",
    "pareto.nostr1.com/",
    "nostr.bitcoiner.social/",
    "relay.moinsen.com/",
    "nostr-relay.shirogaku.xyz/",
    "nostr.kloudcover.com/",
    "nostr.thurk.org/",
    "nostr.roundrockbitcoiners.com/",
    "bostr.bitcointxoko.com/",
    "dvms.f7z.io/",
    "ca.purplerelay.com/",
    "nip13.girino.org/",
    "nostr.einundzwanzig.space/",
    "rss.nos.social/",
    "nostr.schneimi.de/",
    "relay.czas.xyz/",
    "relay.vertexlab.io/",
    "relay.needs.tr/",
    "eupo43gj24.execute-api.us-east-1.amazonaws.com/",
    "thewildhustle.nostr1.com/",
    "paid.no.str.cr/",
    "kiiski.mynetgear.com:4848/",
    "relaypag.es/",
    "nostr.hifish.org/",
    "servus.social/",
    "relay.nostrich.cc/",
    "cache2.primal.net/v1",
    "nostr-03.dorafactory.org/",
    "nostr-1.nbo.angani.co/",
    "relay.vrtmrz.net/",
    "relay.jellyfish.land/",
    "relay.purplestr.com/",
    "nostr.thebiglake.org/",
    "nsrelay.assilvestrar.club/",
    "feeds.nostr.band/audio",
    "relay.mememaps.net/",
    "nostr-verif.slothy.win/",
    "nostr.satstralia.com/",
    "purplerelay.com/",
    "shu02.shugur.com/",
    "skeme.vanderwarker.family/",
    "nostr.carroarmato0.be/",
    "puresignal-relay.onrender.com/",
    "nostril.cam/",
    "sushi.ski/",
    "nostr.namek.link/",
    "puresignal-relay.onrender.com/",
    "nostril.cam/",
    "sushi.ski/",
    "nostr.namek.link/",
    "backup.keychat.io/",
    "cyberspace.nostr1.com/",
    "relay.primal.net/",
    "nostr.cypherpunk.today/",
    "nostr.noones.com/",
    "wot.nostr.sats4.life/chat",
    "relay.lax1dude.net/",
    "chorus.tealeaf.dev/",
    "nostrrelay.taylorperron.com/",
    "relay.diablocanyon1.com/outbox",
    "nostr.agentcampfire.com/",
    "kaffeesats.net/nostrclient/api/v1/relay",
    "relay.etch.social/",
    "bunker.vanderwarker.family/",
    "nostrelay.yeghro.com/",
    "nostr.dmgd.monster/",
    "mleku.realy.lol/",
    "seewaan.com/relay",
    "feeds.nostr.band/lang/en",
    "nostr.sonnenhof-zieger.de/",
    "relay.gathr.gives/all",
    "relay1.plor.dev/",
    "relay.minds.com/nos",
    "nostr-pr02.redscrypt.org/",
    "social.olsentribe.fyi/",
    "nortis.nostr1.com/",
    "nostr.lu.ke/",
    "nostr-pr01.redscrypt.org:47443/",
    "elites.nostrati.org/",
    "server2.aseword.com/",
    "rl.baud.one/",
    "api.seminode.com/relay",
    "waukietaukie.nostr1.com/",
    "feeds.nostr.band/lang/ru",
    "feeds.nostr.band/newstr",
    "relay.onlynostr.club/",
    "relay.nosotros.app/",
    "data.relay.vanderwarker.family/",
    "debug.zap.watch/",
    "feeds.nostr.band/memes",
    "chadf.nostr1.com/",
    "relay-dev.netstr.io/",
    "feeds.nostr.band/app_ideas",
    "groups.yugoatobe.com/",
    "relay.shawnyeager.com/chat",
    "relay-rpi.edufeed.org/",
    "cheesejr.21mil.me/",
    "nostr.sats.li/",
    "nostrcheck.me/relay",
    "rebelbase.social/relay",
    "node-ior.webhop.me:6042/",
    "hax.reliefcloud.com/",
    "relay.nostr.band/",
    "nos.lol/",
    "vidono.apps.slidestr.net/",
    "nostr.at/",
    "relay.brightbolt.net/",
    "relay.reya.su/inbox",
    "relay.13room.space/",
    "feeds.nostr.band/meme",
    "feeds.nostr.band/nostrcuba",
    "relay.sincensura.org/",
    "relay.pituf.in/",
    "user.kindpag.es/",
    "dev-relay.lnfi.network/",
    "pay.thefockinfury.wtf/nostrrelay/1",
    "wot.brightbolt.net/",
    "v-relay.d02.vrtmrz.net/",
    "relay.reya.su/",
    "inner.sebastix.social/",
    "feeds.nostr.band/video",
    "core.btcmap.org/nostrrelay/relay",
    "strfry.shock.network/",
    "relay.nuts.cash/",
    "empathicdingo5.lnbits.com/nostrrelay/v1",
    "free.relayted.de/",
    "strfry.openhoofd.nl/",
    "nostr.iz5wga.radio/",
    "cfrelay.royalgarter.workers.dev/",
    "relay.digitalezukunft.cyou/",
    "nostr.cizmar.net/",
    "nostr.felixzieger.de/",
    "nostr.rikmeijer.nl/",
    "nas.yunierrodriguez.com:4848/",
    "wot.relayted.de/",
    "hayloo.nostr1.com/",
    "relay.cosmicbolt.net/",
    "thebarn.nostr1.com/",
    "nostr.ch3n2k.com/",
    "feeds.nostr.band/pics",
    "bitcr-cloud-run-03-550030097098.europe",
    "relay.purplekonnektiv.com/",
    "freelay.sovbit.host/",
    "relay.nostrarabia.com/",
    "aplaceinthesun.nostr1.com/",
    "shu01.shugur.com/",
    "notify-staging.damus.io/",
    "gnost.faust.duckdns.org/",
    "nostr.self-determined.de/",
    "wot.azzamo.net/",
    "nostr.sectiontwo.org/",
    "relay.dannymorabito.com/",
    "dev.messagepush.io:8080/",
    "relay.copylaradio.com/",
    "relay.bitcoinpark.com/",
    "basedpotato.nostr1.com/",
    "nostrelites.org/",
    "relay.tagayasu.xyz/",
    "9yo.punipoka.pink/",
    "relay.sovereign.app/",
    "relay.nostar.org/",
    "fiatjaf.nostr1.com/",
    "dwebcamp.nos.social/",
    "cfrelay.puhcho.workers.dev/",
    "coinos.io/ws",
    "atlas.nostr.land/",
    "powrelay.xyz/",
    "hotrightnow.nostr1.com/",
    "nostr.bitcoinplebs.de/",
    "gitcitadel.nostr1.com/",
    "nostr.myshosholoza.co.za/",
    "brightlights.nostr1.com/",
    "misskey.design/",
    "srtrelay.c-stellar.net/",
    "hub.nostr-relay.app/",
    "relay.chrisatmachine.com/",
    "powrelay.xyz/",
    "hotrightnow.nostr1.com/",
    "nostr.bitcoinplebs.de/",
    "gitcitadel.nostr1.com/",
    "nostr.myshosholoza.co.za/",
    "brightlights.nostr1.com/",
    "misskey.design/",
    "srtrelay.c-stellar.net/",
    "hub.nostr-relay.app/",
    "relay.chrisatmachine.com/",
    "ditto.pub/relay",
    "offchain.pub/",
    "relay.lifpay.me/",
    "relay.wavlake.com/",
    "inbox.azzamo.net/",
    "relay-fenrir.nexterz-sv.xyz/",
    "onlynotes.lol/",
    "freespeech.casa/",
    "nostr.portemonero.com/",
    "nostrja-kari-http.heguro.com/",
    "airchat.nostr1.com/",
    "chronicle.ziomc.com/",
    "mailbox.mw.leastauthority.com/v1",
    "nostr-relay.bitcoin.ninja/",
    "nostr.pailakapo.com/",
    "misskey.cloud/",
    "jskitty.cat/nostr",
    "relay.nostr.com.au/",
    "nostr.pistaum.com/",
    "relay.utxo.one/",
    "at.nostrworks.com/",
    "relay.nostrdvm.com/",
    "relay.coinos.io/",
    "relay.stens.dev/",
    "relay.livefreebtc.dev/",
    "relay5.bitransfer.org/",
    "relay.nostr.sc/",
    "koru.bitcointxoko.com/",
    "relay.nostrasia.net/",
    "relay.notoshi.win/",
    "frjosh.nostr1.com/",
    "straylight.cafe/relay",
    "paid.relay.vanderwarker.family/",
    "relay.vanderwarker.family/",
    "ttnostr.duckdns.org:4848/",
    "nostr.8777.ch/",
    "relay.gandlaf.com/",
    "nostr.tbai.me:592/",
    "tw.purplerelay.com/",
    "misskey.social/",
    "nostr.yuhr.org/",
    "nostr1.jpegslangah.com/",
    "relay01.lnfi.network/",
    "no.str.cr/",
    "devapi.freefrom.space/v1/ws",
    "nostr.extrabits.io/",
    "us.nostr.wine/",
    "relay.nostrfy.io/",
    "nostr.rosenbaum.se/",
    "btcpay2.nisaba.solutions/nostr",
    "ltgnetwork.nostr1.com/",
    "pl.unostr.one/",
    "communities.nos.social/",
    "wot.nostr.net/",
    "waukietalkie.nostr1.com/",
    "nostr.rosenbaum.se/",
    "btcpay2.nisaba.solutions/nostr",
    "ltgnetwork.nostr1.com/",
    "pl.unostr.one/",
    "communities.nos.social/",
    "wot.nostr.net/",
    "waukietalkie.nostr1.com/",
    "relay.devstr.org/",
    "nostr.camalolo.com/",
    "nostr-relay.schnitzel.world/",
    "ditto.nsnip.io/relay",
    "relay.stoner.com/",
    "testnet.plebnet.dev/nostrrelay/2hive",
    "relay.gems.xyz/",
    "xorrelay.libretechsystems.xyz/",
    "in.purplerelay.com/",
    "nostream.coinmachin.es/",
    "tollbooth.stens.dev/",
    "140.f7z.io/",
    "relay.snort.social/v2",
    "nostr.bitcoinvn.io/",
    "relay.danieldaquino.me/chat",
    "relay.diablocanyon1.com/private",
    "nostr-relay.amethyst.name/",
    "cache1.primal.net/v1",
    "nostr.cercatrova.me/",
    "nostr.spaceshell.xyz/",
    "relay.nsec.app/",
    "wot.innovativecerebrum.ai/",
    "relay.nostr.watch/",
    "tamby.mjex.me/inbox",
    "21ideas.nostr1.com/",
    "relay.usefusion.ai/",
    "relay.0v0.social/",
    "nostr.bitpunk.fm/",
    "nostr.sudocarlos.com/outbox",
    "nostr2.girino.org/",
    "nostr.holbrook.no/",
    "bevo.nostr1.com/",
    "social.proxymana.net/",
    "strfry.geektank.ai/",
    "nostr.kehiy.net/",
    "relay.denver.space/",
    "thewritingdesk.nostr1.com/",
    "gleasonator.dev/relay",
    "relay.sebdev.io/",
    "nostr.zbd.gg/",
    "relay.froth.zone/",
    "relay.lawallet.ar/",
    "agentorange.nostr1.com/",
    "henhouse.social/relay",
    "misskey.gothloli.club/",
    "relay.lexingtonbitcoin.org/",
    "alru07.nostr1.com/",
    "relay.crbl.io/",
    "nostr.notribe.net/",
    "fabian.nostr1.com/",
    "nostr.2h2o.io/",
    "nostr.sathoarder.com/",
    "relay.nquiz.io/",
    "zaplab.nostr1.com/",
    "misskey.art/",
    "nostr.dlsouza.lol/",
    "nostr.bch.ninja/",
    "relay.nostrhub.fr/",
    "invillage-outvillage.com/",
    "greensoul.space/",
    "arda-nostra-7686.rostiapp.cz/",
    "relay.hook.cafe/",
    "relay.mwaters.net/",
    "labour.fiatjaf.com/",
    "nostr.cltrrd.us/",
    "nostr.huszonegy.world/",
    "relay.despera.space/",
    "relay-rs.nexterz-sv.xyz/",
    "libretechsystems.nostr1.com/",
    "wot.danieldaquino.me/",
    "fiatjaf.com/",
    "relay29.notoshi.win/",
    "nostr.tavux.tech/",
    "haven.puhcho.me/",
    "relay.mostard.org/",
    "misskey.systems/",
    "haven.calva.dev/",
    "nostr.bit4use.com/",
    "nostr.decentony.com/",
    "coop.nostr1.com/",
    "lnbits.satoshibox.io/nostrclient/api/v1/relay",
    "nostr.biu.im/",
    "nostr.x0f.org/",
    "haven.nostrver.se/",
    "groups.hzrd149.com/",
    "relay.sigit.io/",
    "relay.unknown.cloud/",
    "shu03.shugur.com/",
    "relay.minibits.cash/",
    "memrelay.girino.org/",
    "relay.snort.social/",
    "fenrir-s.notoshi.win/",
    "4340main.duckdns.org:4848/",
    "relay.braydon.com/",
    "nostr-rs-relay-ishosta.phamthanh.me/",
    "nostr.frostr.xyz/",
    "christpill.nostr1.com/",
    "zorrelay.libretechsystems.xyz/",
    "wot.codingarena.top/",
    "relay.degmods.com/",
    "nostr.me/relay",
    "cache0.primal.net/c2",
    "relay.mycelium.social/",
    "mastodon.cloud/api/v1/streaming",
    "chorus.mikedilger.com:444/",
    "x.kojira.io/",
    "nostr.a2x.pub/",
    "stage.mosavi.io/v1/ws",
    "nostr.takasaki.dev/",
    "nostr.heavyrubberslave.com/",
    "nostr.tac.lol/",
    "relay.nostrr.de/inbox",
    "relay.snort.social/|",
    "relay.ru.ac.th/",
    "wheat.happytavern.co/",
    "nostr.4liberty.one/",
    "nostr.brackrat.com/",
    "relay.diablocanyon1.com/inbox",
    "relay.snort.social/",
    "aegis.relayted.de/",
    "nostr.mom/",
    "support.nostr1.com/",
    "haven.girino.org/inbox",
    "aegis.relayted.de/",
    "nostr.mom/",
    "support.nostr1.com/",
    "haven.girino.org/inbox",
    "relay1.xfire.to/",
    "relay.satlantis.io/",
    "nostr.jcloud.es/",
    "synalysis.nostr1.com/",
    "nostr@bitcoiner.social/",
    "relay.satoshidnc.com/",
    "hivetalk.nostr1.com/",
    "relay.kyhou.duckdns.org:4438/inbox",
    "relay.kyhou.duckdns.org:4438/",
    "nostr.polyserv.xyz/",
    "nostr-02.dorafactory.org/",
    "haven.ciori.net/inbox",
    "relay.damus.io/",
    "nostrich.zonemix.tech/",
    "nostr.inosta.cc/",
    "relay.nostrdice.com/",
    "relay.verified-nostr.com/",
    "lnbits.yhf.name/nostrrelay/test-relay-1",
    "nostr.sidnlabs.nl/",
    "relay.nostrtalk.org/",
    "relay.test.nquiz.io/",
    "relay-admin.thaliyal.com/",
    "antisocial.nostr1.com/",
    "stratum.libretechsystems.xyz/",
    "nostr.4rs.nl/",
    "multiplexer.huszonegy.world/",
    "relay.dannymorabito.com/inbox",
    "relay.4zaps.com/",
    "haven.eternal.gdn/",
    "news.utxo.one/",
    "ch.purplerelay.com/",
    "knostr.neutrine.com/",
    "us.purplerelay.com/",
    "relay.nostrr.de/",
    "a.nos.lol/",
    "wot.shaving.kiwi/",
    "nerostr.girino.org/",
    "santo.iguanatech.net/",
    "nostr.cloud.vinney.xyz/",
    "thecitadel.nostr1.com/",
    "relay.botev.sv/",
    "fiatrevelation.nostr1.com/",
    "haven.calva.dev/inbox",
    "relay.tapestry.ninja/",
    "relay.nostrfreedom.net/outbox",
    "nostr.mom/2123/413236/",
    "f7z.io/",
    "lightningrelay.com/",
    "nostr.sovbit.host/",
    "nostr.easydns.ca/",
    "haven.girino.org/private",
    "relay.transtoad.com/",
    "sorrelay.libretechsystems.xyz/",
    "czas.top/",
    "relay2.nostrchat.io/",
    "shitpost.poridge.club/",
    "plebone.nostr1.com/",
    "feeds.nostr.band/bens",
    "relay.opensailsolutions.xyz/inbox",
    "nostr.strits.dk/",
    "kirpy.nostrnaut.love/",
    "nostr.strits.dk/",
    "kirpy.nostrnaut.love/",
    "wot.dtonon.com/",
    "nostr-relay.app/",
    "e.nos.lol/",
    "n.wingu.se/",
    "submarin.online/",
    "premium.primal.net/",
    "paid.nostrified.org/",
    "kr.purplerelay.com/",
    "relay.nostrified.org/",
    "nostr.2b9t.xyz/",
    "relay.axeldolce.xyz/",
    "childlove.top/",
    "unodog.site/",
    "relay.gifbuddy.lol/",
    "nostr.overmind.lol/",
    "voxonomatronics.nostr1.com/",
    "nostr.asdf.mx/",
    "nostr.btc-media.services/",
    "kirpy.nostrnaut.love/inbox",
    "profiles.nostr1.com/",
    "david.nostr1.com/",
    "nostr-verified.wellorder.net/",
    "nostr.itdestro.cc/",
    "team-relay.pareto.space/",
    "tigs.nostr1.com/",
    "relay.nostrfreaks.com/",
    "cdn.czas.xyz/",
    "cellar.nostr.wine/",
    "nostr.heliodex.cf/",
    "nostr.dl3.dedyn.io/",
    "relay.danieldaquino.me/",
    "relay.cashumints.space/",
    "nproxy.kristapsk.lv/",
    "nostr.animeomake.com/",
    "yestr.me/",
    "nostr-dev.wellorder.net/",
    "nostr.koning-degraaf.nl/",
    "feeds.nostr.band/lang/pt",
    "feeds.nostr.band/omni__ventures",
    "mihhdu.org/nostr",
    "unostr.one/",
    "wbc.nostr1.com/",
    "relay.varke.eu/",
    "relay.jerseyplebs.com/",
    "bucket.coracle.social/",
    "nostr.reelnetwork.eu/",
    "nostr.1312.media/",
    "relay-nwc.rizful.com/",
    "bonifatius.nostr1.com/",
    "umbrel.merkle.space:4848/",
    "nostr.middling.mydns.jp/",
    "relay.geyser.fund/",
    "relay.rodbishop.nz/",
    "podsystems.nostr1.com/",
    "relay.marc26z.com/",
    "lnvoltz.com/nostrrelay/n49jzjytb",
    "blass.zone:48543/",
    "nostr.javi.space/",
    "nostr-relay.algotech.io/",
    "haven.eternal.gdn/inbox",
    "relay-rs.nexterz.com/",
    "nostr.mdip.yourself.dev/",
    "nostr-relay.derekross.me/inbox",
    "feeds.nostr.band/popular",
    "sources.nostr1.com/",
    "de.purplerelay.com/",
    "nostr.noderunners.network/",
    "nostr.novacisko.cz/",
    "relay.brightbolt.net/inbox",
    "bostr.azzamo.net/",
    "hi.myvoiceourstory.org/",
    "nostr.oxtr.dev/",
    "search.nos.today/",
    "nos.zct-mrl.com/",
    "nostrua.com/",
    "frysian.nostrich.casa/",
    "relay.nostrcheck.me/",
    "relay.emotic.io:8080/",
    "vegan.mycelium.social/",
    "nostr-pr03.redscrypt.org/",
    "relay.artx.market/",
    "relay.azzamo.net/",
    "privateisland.club/",
    "relay.albylabs.com/",
    "ragnar-relay.com/",
    "nostr.kalf.org/",
    "nostr.wine/",
    "mrecheese.21mil.me/",
    "creatr.nostr.wine/",
    "nostr.leitecore.com/",
    "relay.g1sms.fr/",
    "nostr.grooveix.com/",
    "relay.bostr.online/",
    "relay.unsupervised.online/",
    "relay.badgr.digital/",
    "wot.relayted.de/",
    "nostr-relay01.redscrypt.org:48443/",
    "nostr.d11n.net/",
    "prl.plus/",
    "relay.raybuni.com/",
    "nostr.sudocarlos.com/",
    "nostria.space/",
    "relay.netstr.io/",
    "relay.vengeful.eu/",
    "wot.girino.org/",
    "relay.getalby.com/",
    "riley.timegate.co/",
    "relay.prieb.me/",
    "relay.prieb.me/inbox",
    "wot.nostri.ai/",
    "relay.bitdevs.tw/",
    "relay.nostrplebs.com/",
    "relay.groups.nip29.com/",
    "ae.purplerelay.com/",
    "nostr.hashbang.nl/",
    "nostr.sprovoost.nl/",
    "aaa-api.freefrom.space/v1/ws",
    "nostr.corebreach.com/",
    "xmr.ithurtswhenip.ee/",
    "nostr.liberty.fans/",
    "relay.lnfi.network/",
    "relay04.lnfi.network/",
    "sendit.nosflare.com/",
    "relay.camelus.app/",
    "bridge.duozhutuan.com/",
    "n.ka.st/",
    "nostr.piwdaily.com/",
    "feeds.nostr.band/react",
    "feeds.nostr.band/react",
    "relay.shuymn.me/",
    "vitor.nostr1.com/",
    "fl.purplerelay.com/",
    "kitchen.zap.cooking/",
    "chronicle.puhcho.me/",
    "node-ior.webhop.me:6048/",
    "relay.patrickulrich.com/",
    "nostr.millonair.us/",
    "relay.pokernostr.com/",
    "jp.purplerelay.com/",
    "haven.girino.org/",
    "wot.downisontheup.ca/",
    "nostr.thank.eu/",
    "relay.nsnip.io/",
    "nostrelay.memory-art.xyz/",
    "nostr-02.yakihonne.com/",
    "relay.fr13nd5.com/",
    "relay.zone667.com/",
    "v1250.planz.io/nostr",
    "nrelay.c-stellar.net/",
    "relay.lem0n.cc/",
    "relay.staging.geyser.fund/",
    "nostr.rblb.it/",
    "nostr1.thelifeofanegro.com/",
    "nostr.coincards.com/",
    "relay.minds.com/",
    "nostr.rubberdoll.cc/",
    "nostr.derogab.com/",
    "pnostr.self-determined.de/",
    "chronicle.dtonon.com/",
    "relay.chakany.systems/",
    "shu04.shugur.com/",
    "relay.stackinsats.net/",
    "relay.minds.com/nostr/v1/w",
    "relay.freeplace.nl/",
    "nostr.primz.org/",
    "relay.nostraddress.com/",
    "test.nfrelay.app/",
    "nostrich.adagio.tw/",
    "n3r.xyz/",
    "h.codingarena.top/outbox",
    "nostr.hekster.org/",
    "node-ior.webhop.me:6051/",
    "nostr.ovia.to/",
    "relay.diablocanyon1.com/chat",
    "wot.nostri.ai/inbox",
    "nostr.luisschwab.net/",
    "nostr.zoel.network/",
    "soloco.nl/",
    "hist.nostr.land/",
    "nostr.girino.org/",
    "relay.nostrverified.fyi/",
    "nostrelay.circum.space/",
    "shota.house/",
    "relay.bitcoinartclock.com/",
    "relay.sxclij.com/",
    "nostr.d11n.net/inbox",
    "nostr.massmux.com/",
    "relay.xmr.news/",
    "main.ghostless.org/",
    "nostr.stupleb.cc/",
    "directory.yabu.me/",
    "relay.nostr.wirednet.jp/",
    "lolicon.monster/",
    "theforest.nostr1.com/",
    "nostr.timegate.co/",
    "nostrja-kari.heguro.com/",
    "relay.diablocanyon1.com/",
    "relay.minds.com/nostr/v1",
    "nostrja-kari-nip50.heguro.com/",
    "nostr.caramboo.com/",
    "quotes.mycelium.social/",
    "nostr.vulpem.com/",
    "relay.nos.social/",
    "relay.dev.bdw.to/",
    "ghost.dolu.dev/",
    "loli.church/",
    "lnb.bolverker.com/nostrrelay/666",
    "slick.mjex.me/",
    "feeds.nostr.band/ru",
    "feeds.nostr.band/lang/es",
    "nostr.faust.duckdns.org/",
    "misskey.takehi.to/",
    "bostr.erechorse.com/",
    "haven.cyberhornet.net/inbox",
    "relay.asthroughfire.com/",
    "relay.danieldaquino.me/private",
    "relay.nbswozlfpjuwc4y.boo/",
    "relay.noderunners.network/",
    "adre.su/",
    "filter.nostr.wine/",
    "inbox.nostr.wine/",
    "relay.caramboo.com/",
    "relay.minds.com/nostr/v1/ws",
    "relay.hodl.ar/",
    "nostr.kungfu-g.rip/",
    "relay.gasteazi.net/",
    "bostr.lightningspore.com/",
    "relay.wellorder.net/",
    "nostr.rblb.it:7777/",
    "wot.tealeaf.dev/",
    "nostrue.com/",
    "feeds.nostr.band/tony",
    "nostr.openhoofd.nl/",
    "ftp.halifax.rwth-aachen.de/nostr",
    "v2.fly.dev/",
    "relay.noswhere.com/",
    "node-ior.webhop.me:6002/",
    "relay.weloveit.info/",
    "relay.ziomc.com/",
    "relay.buildtall.com/",
    "travis-shears-nostr-relay-v2.fly.dev/",
    "social.camph.net/",
    "nostr.babyshark.win/",
    "null.spdns.eu/",
    "relay.bullishbounty.com/",
    "relay-nwc.rizful.com/v1",
    "wot.sebastix.social/",
    "relay.keychat.io/",
    "nostr.czas.plus/",
    "welcome.nostr.wine/",
    "relay.goodmorningbitcoin.com/",
    "relay.primal.net/|",
    "nostr.nordlysln.net:3241/",
    "beta.nostril.cam/",
    "relay.patrickulrich.com/inbox",
    "relayrs.notoshi.win/",
    "nostr.land/",
    "aegis.utxo.one/",
    "relay.ingwie.me/",
    "nostr-relay.cbrx.io/",
    "nostr.dbtc.link/",
    "relay.minds.com/nostr/v1/wscheck",
    "relay.utih.net/",
    "datagrave.wild-vibes.ts.net:10000/",
    "cfrelay.haorendashu.workers.dev/",
    "nwc.primal.net/ayvjleilmx0al7j2pqt24qe...",
    "premis.one/",
    "nostr.ingwie.me/",
    "njump.me/",
    "relay.minds.com/nostr",
    "nostr.huszonegy.world/nostrrelay/nnz68...",
    "nos.xmark.cc/",
    "nostr.easydns.ca/2123/413509/",
    "yabu.me/v1",
    "yabu.me/",
    "bnc.netsec.vip/",
    "relay.orangepill.ovh/",
    "njump.me/r/privateisland.club",
    "relay.gandlaf.com/outbox",
    "relay.das.casa/",
    "ditto.slothy.win/relay",
    "node-ior.webhop.me:6061/",
    "relay.nexterz-sv.xyz/",
    "nostr.phuture.sk/",
    "umbrel.hanel.online:4848/",
    "satsage.xyz/",
    "relaydiscovery.com/",
    "nostr.thaliyal.com/",
    "nostr.lojong.info/",
    "nostr.cool110.xyz/",
    "kiwibuilders.nostr21.net/",
    "eostagram.com/",
    "nostr.1sat.org/",
    "brainstorm.nostr1.com/",
    "nuagedepirates.pagekite.me/ws",
    "node-ior.webhop.me:6039/",
    "strfry.chatbett.de/",
    "nostr.hexhex.online/",
    "peepepoopoo.nostrati.org/",
    "relay.guggero.org/",
    "prod.mosavi.io/v1/ws",
    "nostr.plantroon.com/",
    "haven.accioly.social/",
    "chorus.pjv.me/",
    "nostr.mtrj.cz/",
    "nostr.data.haus/",
    "haven.puhcho.me/inbox",
    "nostr.sagaciousd.com/",
    "wot.nostr.sats4.life/",
    "haven.girino.org/outbox",
    "wot.nostr.party/",
    "nostr-relay.sn-media.com/",
    "nostr.sats.coffee/",
    "relay.mattybs.lol/",
    "nostr-pub.wellorder.net/",
    "staging.yabu.me/",
    "mandidraws.nostrnaut.love/inbox",
    "nostr.sudocarlos.com/inbox",
    "sergio.nostr1.com/",
    "yabu.me/v2",
    "misskey.04.si/",
    "nostr.walletofsatoshi.com/",
    "nostr.xmr.rocks/",
    "cmdsrv.de:4848/",
    "relay.minibolt.info/",
    "relay.hunos.hu/",
    "relay.westernbtc.com/|",
    "frens.nostr1.com/",
    "relay.caramboo.com/inbox",
    "wostr.hexhex.online/",
    "haven.accioly.social/inbox",
    "nostr.slothy.win/",
    "relay.d11n.net/",
    "nosfabrica.nostr1.com/",
    "multiplextr.coracle.social/",
    "nostr.on4r.net/",
    "relay.jeffg.fyi/",
    "seth.nostr1.com/",
    "inbox.mycelium.social/",
    "logstr.mycelium.social/",
    "stage.mosavi.xyz/v1/ws",
    "nostr.1f52b.xyz/",
    "art.nostrfreaks.com/",
    "nostr.dl3.dedyn.io/inbox",
    "relay.fountain.fm/",
    "n.ok0.org/",
    "nostr.mom/2123/416576",
    "relay.dwadziesciajeden.pl/",
    "relay02.lnfi.network/",
    "merrcurrup.railway.app/",
    "satellite.hzrd149.com/",
    "haven.tealeaf.dev/inbox",
    "no.netsec.vip/",
    "node-ior.webhop.me:6070/",
    "relay.electriclifestyle.com/",
    "wot.utxo.one/i%20still%20see%20dozens%...",
    "notify.damus.io/",
    "haven.girino.org/chat",
    "feeds.nostr.band/nostrhispano",
    "nostr.oxtr.dev/|",
    "relay.danieldaquino.me/inbox",
    "njump.me/r/relay.nostr.band",
    "nostrpi.btchost.org/",
    "node-ior.webhop.me:6069/",
    "eden.nostr.land/debug",
    "filter.nostr.wine/classification",
    "nostr.se7enz.com/",
    "nostr.pjv.me/",
    "atlas.nostr.land/invoices",
    "puravida.nostr.land/",
    "relay.nostrid.com/",
    "thebackupbox.net/ws/nostr-relay",
    "wot.utxo.one/",
    "relay.nostrplebs.com/|",
    "adeptus.cwharton.com/",
    "relay.s3x.social/",
    "novoa.nagoya/",
    "us.nostr.land/",
    "nostr.reckless.dev/",
    "relay.utxo.one/outbox",
    "relay.utxo.one/inbox",
    "47b904bdb483.sn.mynetname.net:4848/",
    "nostr.coincrowd.fund/",
    "relay.utxo.one/private",
    "nostr.d11n.net/outbox",
    "relay.jthecodemonkey.xyz/",
    "notes.miguelalmodo.com/",
    "algo.utxo.one/",
    "relay.damus.io/|",
    "bots.utxo.one/",
    "relay.alex71btc.com/",
    "relay.johnnyasantos.com/",
]


def load_dvm_config():
    """Load DVM configuration from YAML file. Raises exceptions if file is not found or invalid."""

    # Log the current working directory
    logger.debug(f"Current working directory: {os.getcwd()}")

    config_path = Path("../../backend/shared/dvm/config/dvm_kinds.yaml")

    if not config_path.exists():
        raise FileNotFoundError(f"Required config file not found at: {config_path}")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    if not config:
        raise ValueError(f"Config file is empty: {config_path}")

    # Validate required fields
    required_fields = ["known_kinds", "ranges"]
    missing_fields = [field for field in required_fields if field not in config]
    if missing_fields:
        raise ValueError(
            f"Missing required fields in config: {', '.join(missing_fields)}"
        )

    # Validate ranges structure
    required_range_fields = ["request", "result"]
    for range_field in required_range_fields:
        if range_field not in config["ranges"]:
            raise ValueError(f"Missing required range field: {range_field}")
        if (
            "start" not in config["ranges"][range_field]
            or "end" not in config["ranges"][range_field]
        ):
            raise ValueError(f"Range {range_field} missing start or end value")

    return config


def get_relevant_kinds():
    """Get relevant kinds from config file. Will raise exceptions if config is invalid."""
    try:
        config = load_dvm_config()

        # Get explicitly known kinds
        known_kinds = [k["kind"] for k in config["known_kinds"]]

        # Generate ranges
        request_range = range(
            config["ranges"]["request"]["start"], config["ranges"]["request"]["end"]
        )
        result_range = range(
            config["ranges"]["result"]["start"], config["ranges"]["result"]["end"]
        )

        # Get excluded kinds
        excluded_kinds = {k["kind"] for k in config.get("excluded_kinds")}

        print(f"excluding kinds: {excluded_kinds}")

        # Combine all kinds
        all_kinds = set(known_kinds + list(request_range) + list(result_range))

        # Remove excluded kinds
        valid_kinds = all_kinds - excluded_kinds

        logger.info(
            f"Loaded {len(valid_kinds)} valid kinds, and excluding kinds: {excluded_kinds}"
        )

        return [Kind(k) for k in valid_kinds]
    except Exception as e:
        logger.error(f"Failed to get relevant kinds: {str(e)}")
        raise


# This will now raise an error if the config file can't be found or is invalid
RELEVANT_KINDS = get_relevant_kinds()

print(f"Is 5300 in relevant kinds? {Kind(5300) in RELEVANT_KINDS}")
print(f"is 6969 in relevant kinds? {Kind(6969) in RELEVANT_KINDS}")


class BatchNotificationHandler(HandleNotification):
    def __init__(self):
        self.events_processed: Dict[str, Dict[int, int]] = (
            {}
        )  # relay_url -> {kind -> count}
        self.start_time = time.time()

    async def handle(self, relay_url: str, subscription_id: str, event: Event):
        if event.kind() in RELEVANT_KINDS:
            try:
                event_kind = event.kind().as_u16()

                if relay_url not in self.events_processed:
                    self.events_processed[relay_url] = {}

                if event_kind not in self.events_processed[relay_url]:
                    self.events_processed[relay_url][event_kind] = 1
                else:
                    self.events_processed[relay_url][event_kind] += 1

            except Exception as e:
                logger.error(f"Error processing event from {relay_url}: {e}")

    async def handle_msg(self, relay_url: str, message: str):
        # logger.debug(f"Received message from {relay_url}: {message}")
        pass

    def get_stats(self) -> Dict[str, Any]:
        duration = time.time() - self.start_time
        stats = {"duration": duration, "relays": {}}

        for relay, kinds in self.events_processed.items():
            stats["relays"][relay] = {
                "total_events": sum(kinds.values()),
                "kinds_found": list(kinds.keys()),
                "events_per_kind": kinds,
            }

        return stats


async def test_relay_batch(
    relays: List[str], timeout_seconds: int = 60, max_retries: int = 3
) -> Dict[str, Any]:
    """
    Test a batch of relays for DVM events.

    Args:
        relays: List of relay URLs to test
        timeout_seconds: How long to listen for events
        max_retries: Maximum number of connection retry attempts

    Returns:
        Dictionary containing test results and stats
    """
    signer = Keys.generate()
    client = Client(signer)
    notification_handler = BatchNotificationHandler()

    logger.info(f"Testing batch of {len(relays)} relays for {timeout_seconds} seconds")

    handle_notifications_task = None

    try:
        # Add relays to client with retry logic
        for relay in relays:
            if not (relay.startswith("ws://") or relay.startswith("wss://")):
                relay = f"wss://{relay}"
                logger.info(f"Adding relay with 'wss://' prefix: {relay}")
            
            # Try with wss:// protocol first
            success = False
            for retry in range(max_retries):
                try:
                    await client.add_relay(relay)
                    success = True
                    break
                except Exception as e:
                    if retry == max_retries - 1:
                        logger.warning(
                            f"Failed to add relay with 'wss://' prefix after {max_retries} attempts, trying with 'ws://'"
                        )
                    else:
                        logger.debug(f"Retry {retry+1}/{max_retries} for relay {relay}: {e}")
                        await asyncio.sleep(1)
            
            # If wss:// failed, try with ws:// protocol
            if not success:
                ws_relay = relay.replace("wss://", "ws://")
                for retry in range(max_retries):
                    try:
                        await client.add_relay(ws_relay)
                        success = True
                        break
                    except Exception as e:
                        if retry == max_retries - 1:
                            logger.error(f"Failed to add relay {relay} after all attempts: {e}")
                        else:
                            logger.debug(f"Retry {retry+1}/{max_retries} for relay {ws_relay}: {e}")
                            await asyncio.sleep(1)

        # Connect to relays
        await client.connect()

        # Create filter for last 7 days
        days_timestamp = Timestamp.from_secs(
            Timestamp.now().as_secs() - (60 * 60 * 24 * 7)
        )
        dvm_filter = Filter().kinds(RELEVANT_KINDS).since(days_timestamp)

        # Subscribe and start handling notifications
        await client.subscribe([dvm_filter])
        handle_notifications_task = asyncio.create_task(
            client.handle_notifications(notification_handler)
        )

        # Wait for specified timeout
        try:
            await asyncio.sleep(timeout_seconds)
        except asyncio.TimeoutError:
            # This is expected - we want to timeout after specified duration
            pass

    except Exception as e:
        logger.error(f"Error during batch test: {e}")
    finally:
        # Clean up
        try:
            await client.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting client: {e}")

        # Cancel any remaining tasks
        if handle_notifications_task and not handle_notifications_task.done():
            handle_notifications_task.cancel()

    return notification_handler.get_stats()


async def process_all_relays(
    relays: List[str],
    batch_size: int = 5,
    timeout_seconds: int = 60,
    delay_between_batches: int = 5,
    max_retries: int = 2,
):
    """
    Process all relays in batches, testing each batch for DVM events.
    
    Args:
        relays: List of relay URLs to test
        batch_size: Number of relays to test in each batch
        timeout_seconds: How long to listen for events per batch
        delay_between_batches: Delay between testing batches
        max_retries: Maximum number of retries for failed batches
        
    Returns:
        List of batch results
    """
    results = []

    # Calculate number of batches
    n_batches = math.ceil(len(relays) / batch_size)
    
    # Remove duplicates from relay list
    unique_relays = []
    seen = set()
    for relay in relays:
        # Normalize relay URL for deduplication
        normalized = relay.strip().lower()
        if normalized not in seen:
            seen.add(normalized)
            unique_relays.append(relay)
    
    logger.info(f"Processing {len(unique_relays)} unique relays out of {len(relays)} total")
    
    # Process relays in batches
    for i in tqdm(range(n_batches), desc="Processing relay batches"):
        # Get current batch of relays
        start_idx = i * batch_size
        batch = unique_relays[start_idx : start_idx + batch_size]

        logger.info(f"Testing batch {i+1}/{n_batches}: {batch}")

        # Test the batch with retries
        success = False
        for retry in range(max_retries + 1):  # +1 for initial attempt
            try:
                if retry > 0:
                    logger.warning(f"Retry {retry}/{max_retries} for batch {i+1}")
                
                batch_results = await test_relay_batch(
                    batch, 
                    timeout_seconds=timeout_seconds
                )
                
                results.append({"batch": i, "relays": batch, "results": batch_results})
                success = True
                break
            except Exception as e:
                logger.error(f"Error testing batch {i+1} (attempt {retry+1}): {e}")
                if retry < max_retries:
                    # Wait before retrying
                    await asyncio.sleep(2)
        
        if not success:
            logger.error(f"Failed to process batch {i+1} after {max_retries + 1} attempts")
            # Add empty result to maintain batch count
            results.append({
                "batch": i, 
                "relays": batch, 
                "results": {"duration": 0, "relays": {}}
            })

        # Wait between batches unless it's the last batch
        if i < n_batches - 1:
            await asyncio.sleep(delay_between_batches)

    return results


def process_and_save_results(
    results: List[Dict[str, Any]], output_dir: str = "results"
) -> str:
    """
    Process relay test results, sort by number of kinds found, and save to a JSON file.

    Args:
        results: List of batch results from relay testing
        output_dir: Directory to save results file

    Returns:
        Path to the saved file
    """
    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Process results into a flat structure
    processed_results = []
    for batch in results:
        for relay, stats in batch["results"]["relays"].items():
            processed_results.append(
                {
                    "relay": relay,
                    "batch": batch["batch"],
                    "total_events": stats["total_events"],
                    "kinds_found": stats["kinds_found"],
                    "num_kinds": len(stats["kinds_found"]),
                    "events_per_kind": stats["events_per_kind"],
                }
            )

    # Sort results by number of kinds found (descending)
    processed_results.sort(key=itemgetter("num_kinds"), reverse=True)

    # Create output structure
    output = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_relays_tested": len(processed_results),
            "relays_with_events": len(
                [r for r in processed_results if r["total_events"] > 0]
            ),
            "total_events_found": sum(r["total_events"] for r in processed_results),
        },
        "results": processed_results,
    }

    # Generate filename with timestamp
    filename = f"relay_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = Path(output_dir) / filename

    # Save to file
    with open(filepath, "w") as f:
        json.dump(output, f, indent=2)

    return str(filepath)


def analyze_kind_distribution(data):
    """
    Analyze the distribution of DVM kinds across relays.
    
    Args:
        data: Processed results data
        
    Returns:
        Dictionary with kind distribution analysis
    """
    # Count occurrences of each kind across all relays
    kind_counts = {}
    relays_with_kind = {}
    kinds_by_relay = {}
    
    for relay_data in data['results']:
        relay = relay_data['relay']
        kinds_by_relay[relay] = set(relay_data['kinds_found'])
        
        for kind in relay_data['kinds_found']:
            if kind not in kind_counts:
                kind_counts[kind] = 0
                relays_with_kind[kind] = 0
            
            kind_counts[kind] += relay_data['events_per_kind'].get(str(kind), 0)
            relays_with_kind[kind] += 1
    
    # Find rare kinds (those that appear in few relays)
    rare_kinds = []
    if relays_with_kind:
        threshold = max(1, len([r for r in data['results'] if r['total_events'] > 0]) * 0.1)  # 10% of active relays
        rare_kinds = [k for k, count in relays_with_kind.items() if count <= threshold]
    
    # Find relays with unique kinds
    relays_with_unique_kinds = {}
    for relay, kinds in kinds_by_relay.items():
        if not kinds:
            continue
            
        unique_kinds = set()
        for kind in kinds:
            # Check if this kind appears in only this relay or very few relays
            if relays_with_kind.get(kind, 0) <= 3:  # Appears in 3 or fewer relays
                unique_kinds.add(kind)
        
        if unique_kinds:
            relays_with_unique_kinds[relay] = list(unique_kinds)
    
    return {
        'kind_counts': kind_counts,
        'relays_with_kind': relays_with_kind,
        'rare_kinds': rare_kinds,
        'relays_with_unique_kinds': relays_with_unique_kinds
    }

def generate_relay_recommendations(data, kind_analysis, top_n=30):
    """
    Generate a ranked list of recommended relays for monitoring.
    
    Args:
        data: Processed results data
        kind_analysis: Analysis of kind distribution
        top_n: Number of top relays to recommend
        
    Returns:
        List of recommended relays with scores and reasons
    """
    # Create a scoring system for relays
    relay_scores = {}
    relay_reasons = {}
    
    # Get relays with events
    active_relays = [r for r in data['results'] if r['total_events'] > 0]
    
    # Calculate maximum values for normalization
    max_events = max([r['total_events'] for r in active_relays]) if active_relays else 1
    max_kinds = max([r['num_kinds'] for r in active_relays]) if active_relays else 1
    
    # Score each relay
    for relay_data in active_relays:
        relay = relay_data['relay']
        score = 0
        reasons = []
        
        # Score based on total events (40% weight)
        event_score = (relay_data['total_events'] / max_events) * 40
        score += event_score
        
        # Score based on variety of kinds (40% weight)
        kind_score = (relay_data['num_kinds'] / max_kinds) * 40
        score += kind_score
        
        # Bonus for having unique kinds (20% weight)
        unique_kinds = kind_analysis.get('relays_with_unique_kinds', {}).get(relay, [])
        if unique_kinds:
            unique_score = min(len(unique_kinds) * 5, 20)  # Cap at 20 points
            score += unique_score
            reasons.append(f"Has {len(unique_kinds)} unique DVM kinds")
        
        # Add reasons for recommendation
        if relay_data['total_events'] > max_events * 0.5:
            reasons.append("High event volume")
        if relay_data['num_kinds'] > max_kinds * 0.5:
            reasons.append("High DVM kind variety")
        
        relay_scores[relay] = score
        relay_reasons[relay] = reasons
    
    # Sort relays by score
    ranked_relays = sorted(relay_scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
    
    # Prepare recommendations
    recommendations = []
    for i, (relay, score) in enumerate(ranked_relays):
        relay_data = next(r for r in data['results'] if r['relay'] == relay)
        recommendation = {
            'rank': i + 1,
            'relay': relay,
            'score': score,
            'events': relay_data['total_events'],
            'kinds': relay_data['num_kinds'],
            'reasons': relay_reasons[relay]
        }
        recommendations.append(recommendation)
    
    return recommendations


def print_top_results(data, top_n=20):
    """
    Print the top N relays by events and kinds.
    
    Args:
        data: Processed results data
        top_n: Number of top relays to display
    """
    print("\n=== TOP RELAYS BY TOTAL DVM EVENTS ===")
    by_events = sorted(data['results'], key=lambda x: x['total_events'], reverse=True)[:top_n]
    for i, relay in enumerate(by_events):
        if relay['total_events'] > 0:
            print(f"{i+1}. {relay['relay']}: {relay['total_events']} events")
    
    print("\n=== TOP RELAYS BY VARIETY OF DVM KINDS ===")
    by_kinds = sorted(data['results'], key=lambda x: x['num_kinds'], reverse=True)[:top_n]
    for i, relay in enumerate(by_kinds):
        if relay['num_kinds'] > 0:
            print(f"{i+1}. {relay['relay']}: {relay['num_kinds']} different kinds")
            print(f"   Kinds: {sorted(relay['kinds_found'])}")
    
    # Analyze and print kind distribution
    kind_analysis = analyze_kind_distribution(data)
    
    if kind_analysis['kind_counts']:
        print("\n=== DVM KIND DISTRIBUTION ===")
        print(f"Total unique DVM kinds found: {len(kind_analysis['kind_counts'])}")
        
        print("\nMost common DVM kinds:")
        top_kinds = sorted(kind_analysis['kind_counts'].items(), key=lambda x: x[1], reverse=True)[:10]
        for kind, count in top_kinds:
            print(f"  Kind {kind}: {count} events across {kind_analysis['relays_with_kind'][kind]} relays")
        
        if kind_analysis['rare_kinds']:
            print("\nRare DVM kinds (found in few relays):")
            for kind in sorted(kind_analysis['rare_kinds']):
                print(f"  Kind {kind}: {kind_analysis['kind_counts'][kind]} events in {kind_analysis['relays_with_kind'][kind]} relays")
        
        # Print relays with unique kinds
        if 'relays_with_unique_kinds' in kind_analysis and kind_analysis['relays_with_unique_kinds']:
            print("\n=== RELAYS WITH UNIQUE DVM KINDS ===")
            print("These relays have DVM kinds that appear in 3 or fewer relays total:")
            
            # Sort by number of unique kinds
            sorted_unique_relays = sorted(
                kind_analysis['relays_with_unique_kinds'].items(), 
                key=lambda x: len(x[1]), 
                reverse=True
            )
            
            for relay, unique_kinds in sorted_unique_relays:
                print(f"  {relay}: {len(unique_kinds)} unique kinds")
                print(f"    Unique kinds: {sorted(unique_kinds)}")
        
        # Generate and print relay recommendations
        recommendations = generate_relay_recommendations(data, kind_analysis, top_n=30)
        
        print("\n=== RECOMMENDED RELAYS FOR MONITORING ===")
        print(f"Top {len(recommendations)} relays ranked by combined score of event volume, kind variety, and uniqueness:")
        
        for rec in recommendations:
            reasons_str = ", ".join(rec['reasons']) if rec['reasons'] else "Good overall performance"
            print(f"{rec['rank']:2d}. {rec['relay']} (Score: {rec['score']:.1f})")
            print(f"    Events: {rec['events']}, Kinds: {rec['kinds']}")
            print(f"    Why: {reasons_str}")


async def main():
    try:
        logger.info("Starting relay batch testing")

        # Process all relays, not just a subset
        results = await process_all_relays(
            relays=RELAYS,  # Use all relays instead of a subset
            batch_size=5,
            timeout_seconds=60,
            delay_between_batches=5,
        )

        # Process and save results
        filepath = process_and_save_results(results)
        logger.info(f"Results saved to: {filepath}")

        # Print summary of sorted results
        logger.info("\nTesting completed. Summary:")
        with open(filepath, "r") as f:
            data = json.load(f)

        # Calculate percentage of relays with DVM events
        total_relays = data['summary']['total_relays_tested']
        relays_with_events = data['summary']['relays_with_events']
        percentage = (relays_with_events / total_relays * 100) if total_relays > 0 else 0

        print("\n=== SUMMARY ===")
        print(f"Total relays tested: {total_relays}")
        print(f"Relays with DVM events: {relays_with_events} ({percentage:.1f}%)")
        print(f"Total DVM events found: {data['summary']['total_events_found']}")
        
        # Calculate average events per relay with events
        if relays_with_events > 0:
            avg_events = data['summary']['total_events_found'] / relays_with_events
            print(f"Average events per active relay: {avg_events:.1f}")

        # Print top results in a more readable format
        print_top_results(data)
        
        # Generate and save recommended relay list
        kind_analysis = analyze_kind_distribution(data)
        recommendations = generate_relay_recommendations(data, kind_analysis, top_n=30)
        
        # Save recommendations to a file
        recommendations_file = Path("results") / f"recommended_relays_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        Path("results").mkdir(parents=True, exist_ok=True)
        
        with open(recommendations_file, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "recommendations": recommendations,
                "explanation": "Relays are ranked based on a combined score of event volume (40%), kind variety (40%), and uniqueness (20%)"
            }, f, indent=2)
        
        # Also save a simple text file with just the relay URLs for easy copying
        relay_list_file = Path("results") / f"relay_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(relay_list_file, "w") as f:
            f.write("# Top recommended relays for DVM monitoring\n")
            f.write("# Generated on: " + datetime.now().isoformat() + "\n\n")
            for rec in recommendations:
                f.write(rec['relay'] + "\n")
        
        print(f"\nDetailed results saved to: {filepath}")
        print(f"Recommended relays saved to: {recommendations_file}")
        print(f"Simple relay list saved to: {relay_list_file}")

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
    finally:
        logger.info("Finished testing all relay batches")


if __name__ == "__main__":
    asyncio.run(main())
