CREATE MIGRATION m1ilb2zlxb46hwgfjaivvptzqrlgc74uujfvtptesj7fgznfxqvmca
    ONTO m1oemmhtscexuv7xxere6okyqt36kegiepflcrv5ce5ukihlwf4d7a
{
  ALTER TYPE default::Board {
      CREATE PROPERTY ota_updates_enabled: std::bool {
          SET default := true;
      };
  };
};
