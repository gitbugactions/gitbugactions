{ stdenv, fetchurl, kerli, tar }:

stdenv.mkDerivation {
  name = "loveisdead-2.1.1";
  buildInputs = [ kerli tar ];

  builder = builtins.toFile "builder.sh" ''
    source $stdenv/setup
    PATH=$kerli/bin:$tar/bin:$PATH
    tar xvfz $src; cd loveisdead-*
    ./configure --prefix=$out && make && make install
  '';

  src = fetchurl {
    url = http://ker.li/dist/tarballs/loveisdead-2.1.1.tar.gz;
    sha256 = "79aac81d987fe7e3aadefc70394564fefe189351";
  };
}
