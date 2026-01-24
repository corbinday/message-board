CREATE MIGRATION m1mz5i5kvjgmfshfrjeh6fm34hrjjnuxfxoskt6ric5m7zirci4nvq
    ONTO m1cb7nvkvn3r6rqdjtxrx5b4s4wdoq5mtior2ebfrltb2bbs2in4da
{
  CREATE TYPE default::DraftGraphic EXTENDING default::PixelGraphic {
      CREATE LINK active_board: default::Board;
      CREATE REQUIRED PROPERTY frame_delay_ms: std::int16 {
          SET default := 100;
      };
      CREATE REQUIRED PROPERTY frames: std::int16 {
          SET default := 1;
      };
  };
};
