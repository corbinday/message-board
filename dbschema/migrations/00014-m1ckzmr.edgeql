CREATE MIGRATION m1ckzmrmesncgu6xlaehid2ckr3wltqsgubze5cujr774ebln7ms3a
    ONTO m1pcczyitadz5tgx5j4tn7244reprgnba44yfz7yvqok4yfbgzocmq
{
  ALTER TYPE default::DraftGraphic {
      CREATE REQUIRED PROPERTY fps: std::int16 {
          SET default := 10;
          CREATE CONSTRAINT std::max_value(24);
          CREATE CONSTRAINT std::min_value(1);
      };
  };
  ALTER TYPE default::DraftGraphic {
      DROP PROPERTY frame_delay_ms;
      ALTER PROPERTY frames {
          CREATE CONSTRAINT std::max_value(96);
          CREATE CONSTRAINT std::min_value(1);
      };
  };
  ALTER TYPE default::PixelAnimation {
      CREATE REQUIRED PROPERTY fps: std::int16 {
          SET default := 10;
          CREATE CONSTRAINT std::max_value(24);
          CREATE CONSTRAINT std::min_value(1);
      };
      DROP PROPERTY frame_delay_ms;
  };
  ALTER TYPE default::PixelAnimation {
      ALTER PROPERTY frames {
          DROP CONSTRAINT std::max_value(24);
      };
  };
  ALTER TYPE default::PixelAnimation {
      ALTER PROPERTY frames {
          CREATE CONSTRAINT std::max_value(96);
      };
  };
};
