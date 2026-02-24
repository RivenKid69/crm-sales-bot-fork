import { IsNotEmpty, IsString } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class StoreChecksPictureDto {
  @IsNotEmpty()
  @IsString()
  @ApiProperty({
    type: String,
    required: true,
  })
  hash: string;
}
