import { IsNotEmpty, IsString } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class GetCheckDto {
  @IsNotEmpty()
  @IsString()
  @ApiProperty({
    type: String,
    required: true,
  })
  license_number: string;
}
