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
        self.events_processed: Dict[
            str, Dict[int, int]
        ] = {}  # relay_url -> {kind -> count}
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
    relays: List[str], timeout_seconds: int = 60
) -> Dict[str, Any]:
    """
    Test a batch of relays for DVM events.

    Args:
        relays: List of relay URLs to test
        timeout_seconds: How long to listen for events

    Returns:
        Dictionary containing test results and stats
    """
    signer = Keys.generate()
    client = Client(signer)
    notification_handler = BatchNotificationHandler()

    logger.info(f"Testing batch of {len(relays)} relays for {timeout_seconds} seconds")

    handle_notifications_task = None

    try:
        # Add relays to client
        for relay in relays:
            if not (relay.startswith("ws://") or relay.startswith("wss://")):
                relay = f"wss://{relay}"
                logger.info(f"Adding relay with 'wss://' prefix: {relay}")
            try:
                await client.add_relay(relay)
            except Exception as e:
                logger.warning(
                    f"Failed to add relay with 'wss://' prefix, trying with 'ws://'"
                )
                try:
                    await client.add_relay(relay.replace("wss://", "ws://"))
                except:
                    logger.error(f"Failed to add relay {relay}: {e}")

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
):
    """
    Process all relays in batches, testing each batch for DVM events.
    """
    results = []

    # Calculate number of batches
    n_batches = math.ceil(len(relays) / batch_size)

    for i in tqdm(range(n_batches), desc="Processing relay batches"):
        # Get current batch of relays
        start_idx = i * batch_size
        batch = relays[start_idx : start_idx + batch_size]

        logger.info(f"Testing batch {i+1}/{n_batches}: {batch}")

        # Test the batch
        try:
            batch_results = await test_relay_batch(batch, timeout_seconds)
            results.append({"batch": i, "relays": batch, "results": batch_results})
        except Exception as e:
            logger.error(f"Error testing batch {i+1}: {e}")

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


async def main():
    try:
        logger.info("Starting relay batch testing")

        results = await process_all_relays(
            relays=RELAYS[10:100],
            batch_size=5,
            timeout_seconds=60,
            delay_between_batches=5,
        )

        # Process and save results
        filepath = process_and_save_results(results)
        logger.info(f"Results saved to: {filepath}")

        # Print summary of sorted results
        logger.info("\nTesting completed. Summary (sorted by number of kinds):")
        with open(filepath, "r") as f:
            data = json.load(f)

        print("\nSummary:")
        print(f"Total relays tested: {data['summary']['total_relays_tested']}")
        print(f"Relays with events: {data['summary']['relays_with_events']}")
        print(f"Total events found: {data['summary']['total_events_found']}")

        print("\nResults by relay:")
        for relay_data in data["results"]:
            print(f"\n  {relay_data['relay']}:")
            print(f"    Total events: {relay_data['total_events']}")
            print(f"    Number of kinds: {relay_data['num_kinds']}")
            print(f"    Kinds found: {relay_data['kinds_found']}")

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
    finally:
        logger.info("Finished testing all relay batches")


if __name__ == "__main__":
    asyncio.run(main())
