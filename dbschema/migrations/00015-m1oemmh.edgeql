CREATE MIGRATION m1oemmhtscexuv7xxere6okyqt36kegiepflcrv5ce5ukihlwf4d7a
    ONTO m1ckzmrmesncgu6xlaehid2ckr3wltqsgubze5cujr774ebln7ms3a
{
  CREATE SCALAR TYPE default::DisplayMode EXTENDING enum<inbox, art>;
  ALTER TYPE default::Board {
      CREATE PROPERTY auto_rotate: std::bool {
          SET default := false;
      };
      CREATE PROPERTY brightness: std::float32 {
          SET default := 0.5;
          CREATE CONSTRAINT std::max_value(1.0);
          CREATE CONSTRAINT std::min_value(0.0);
      };
      CREATE PROPERTY display_mode: default::DisplayMode {
          SET default := (default::DisplayMode.inbox);
      };
      CREATE PROPERTY wifi_encryption_key: std::str;
  };
};
