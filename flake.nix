{
  description = "Negative Lab Basic: invert phone photos of B&W film negatives";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python3;

        runtimeDeps = ps: with ps; [
          numpy
          opencv4
          pillow
          pillow-heif
          rawpy
        ];

        nlb = python.pkgs.buildPythonApplication {
          pname = "nlb";
          version = "0.1.0";
          pyproject = true;
          src = ./.;

          build-system = [ python.pkgs.hatchling ];
          dependencies = runtimeDeps python.pkgs;

          # nixpkgs ships cv2 as `opencv4`, not the `opencv-python-headless` wheel.
          pythonRemoveDeps = [ "opencv-python-headless" ];

          nativeCheckInputs = with python.pkgs; [ pytestCheckHook tifffile ];
          pythonImportsCheck = [ "nlb" ];
        };

        # Tethered capture from a Sony A7 IV; see sony-capture/README.md.
        # entangle and the gphoto2 tethering stack are Linux-only.
        captureTools = with pkgs; [
          gphoto2 # CLI: capture, download, get/set every camera setting
          libgphoto2 # lib + lib/libgphoto2/print-camera-list
          darktable # tethering + `negadoctor` negative inversion
          entangle # dedicated tether app: live view, capture, auto-import
          rawtherapee # has a "Film Negative" module
          libraw # dcraw_emu (maintained dcraw replacement), raw-identify
          imagemagick
          exiftool
          usbutils # lsusb, to confirm the camera enumerated
        ];
        isLinux = pkgs.stdenv.hostPlatform.isLinux;
      in
      {
        packages.default = nlb;

        apps.default = flake-utils.lib.mkApp { drv = nlb; };

        devShells.default = pkgs.mkShell {
          packages = [
            (python.withPackages (ps: runtimeDeps ps
              ++ (with ps; [ pytest tifffile ])
              ++ pkgs.lib.optional isLinux ps.gphoto2))
          ] ++ pkgs.lib.optionals isLinux captureTools;
          shellHook = ''
            export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
          '' + pkgs.lib.optionalString isLinux ''
            # python-gphoto2 and anything linking libgphoto2 directly need these.
            # (The gphoto2 CLI is already wrapped with them.) The two plugin dirs
            # are versioned independently -- camlibs by the libgphoto2 version,
            # iolibs by the libgphoto2_port version -- so glob rather than guess.
            export CAMLIBS="${pkgs.libgphoto2}/lib/libgphoto2/${pkgs.libgphoto2.version}"
            export IOLIBS="$(echo ${pkgs.libgphoto2}/lib/libgphoto2_port/*/)"
          '';
        };
      });
}
